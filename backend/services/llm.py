import json
from contextvars import ContextVar
from openai import OpenAI
from backend.config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    GLM_API_KEY, GLM_BASE_URL, GLM_MODEL
)


# Providers and models
AVAILABLE_MODELS = [
    "deepseek-chat", "deepseek-reasoner",
    "deepseek-v4-flash", "deepseek-v4-pro", 
    "GLM-4.7-Flash"
]

# Per-request model override (safe for concurrent requests via asyncio context)
_model_var: ContextVar[str] = ContextVar("deepseek_model", default="deepseek-v4-flash")



def _get_client_config(selection: str):
    """Return the correct OpenAI client and model name for the given selection."""
    if selection.startswith("deepseek"):
        return OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            timeout=120.0,
            max_retries=3
        ), selection

    elif selection == "GLM-4.7-Flash":
        return OpenAI(
            api_key=GLM_API_KEY,
            base_url=GLM_BASE_URL,
            timeout=120.0,
            max_retries=3
        ), GLM_MODEL
    return None, None


    return None, None


def set_model(model: str) -> None:
    """Set the model for the current request context."""
    if model in AVAILABLE_MODELS:
        _model_var.set(model)


def get_model() -> str:
    return _model_var.get()


def _repair_json(s: str) -> str:
    """Attempt to fix common LLM JSON errors like missing or extra closing brackets or unquoted values."""
    s = s.strip()
    if not s:
        return s
    
    # 1. Handle unquoted string values (common with some models)
    # This regex looks for values after a colon that aren't quoted, aren't numbers, and aren't objects/arrays.
    import re
    # Match: ": <content>" where <content> doesn't start with " or [ or { or a number, and ends before , or }
    # We use a non-greedy match and lookahead for , or }
    def quote_val(match):
        val = match.group(1).strip()
        if val.lower() in ["true", "false", "null"]:
            return f': {val}'
        # If it's already quoted, don't double quote
        if val.startswith('"') and val.endswith('"'):
            return f': {val}'
        # If it looks like a number, don't quote
        try:
            float(val)
            return f': {val}'
        except ValueError:
            pass
        # Escape existing quotes inside the new string and wrap in quotes
        safe_val = val.replace('"', '\\"')
        return f': "{safe_val}"'

    s = re.sub(r':\s*([^"\[\{\d\-][^,\}]*)', quote_val, s)

    # 2. Basic balancing: count { vs } and [ vs ]
    stack = []
    fixed_s = ""
    in_string = False
    escaped = False
    
    for i, char in enumerate(s):
        if char == '"' and not escaped:
            in_string = not in_string
        
        if not in_string:
            if char == '{' or char == '[':
                stack.append('}' if char == '{' else ']')
            elif char == '}' or char == ']':
                if stack and stack[-1] == char:
                    stack.pop()
                else:
                    continue
        
        fixed_s += char
        if char == '\\' and not escaped:
            escaped = True
        else:
            escaped = False
    
    # Add missing closings
    while stack:
        fixed_s += stack.pop()
    
    return fixed_s



def _extract_json(s: str) -> dict:
    """Robustly extract and repair JSON from a string."""
    s = s.strip()
    
    # Strip <think>...</think> blocks from reasoning models
    import re
    s = re.sub(r'<think>.*?</think>', '', s, flags=re.DOTALL).strip()
    
    # Strip markdown formatting
    s = re.sub(r'^```json\s*', '', s, flags=re.MULTILINE)
    s = re.sub(r'^```\s*', '', s, flags=re.MULTILINE)
    s = re.sub(r'\s*```$', '', s, flags=re.MULTILINE)
    s = s.strip()

    # 1. Try direct parse

    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        # If the error is 'Extra data', try to truncate
        if "Extra data" in e.msg:
            try:
                return json.loads(s[:e.pos])
            except Exception:
                pass

        # 2. Try to repair the string (handle mismatched brackets)
        try:
            repaired = _repair_json(s)
            return json.loads(repaired)
        except Exception:
            pass

        # 3. Try to find the first '{' and last '}'
        start = s.find('{')
        end = s.rfind('}')
        if start != -1 and end != -1 and end > start:
            candidate = s[start:end+1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as e2:
                if "Extra data" in e2.msg:
                    try:
                        return json.loads(candidate[:e2.pos])
                    except Exception:
                        pass
                
                # Try repairing the candidate
                try:
                    return json.loads(_repair_json(candidate))
                except Exception:
                    pass

        # Re-raise the original error if we couldn't recover
        raise e




def llm_call(system: str, user: str, tool: dict, token_cb=None, thinking_cb=None) -> dict:
    """Single LLM call that enforces a specific function tool and returns parsed args.
    
    token_cb: optional callable(str) called with each streamed token delta (normal content).
    thinking_cb: optional callable(str) called with thinking/reasoning content.
    """
    selection = _model_var.get()
    
    client, model = _get_client_config(selection)
    if not client:
        raise RuntimeError(f"Unsupported model selection: {selection}")

    # DeepSeek V4 API currently returns 400 errors for strict tool_choice on both flash and pro models.
    # We will use Prompt Engineering (JSON mode) for them.
    supports_tools = selection not in ["deepseek-reasoner", "deepseek-v4-pro", "deepseek-v4-flash"]

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]

    if not supports_tools:
        schema_str = json.dumps(tool["function"].get("parameters", {}), ensure_ascii=False)
        messages[0]["content"] += (
            f"\n\n[CRITICAL INSTRUCTION]\n"
            f"You MUST output ONLY valid JSON. The JSON must exactly match this JSON Schema:\n{schema_str}\n"
            f"Do NOT wrap the output in a 'parameters' or '{tool['function']['name']}' key. Return the raw properties object directly.\n"
            f"Do NOT include Markdown blocks (e.g. ```json), explanations, or any other text."
        )

    retries = 2
    last_error = None

    for attempt in range(retries + 1):
        try:
            if supports_tools:
                stream = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=[tool],
                    tool_choice={"type": "function", "function": {"name": tool["function"]["name"]}},
                    stream=True,
                )
                args_str = ""
                _tool_call_id = None
                _tool_call_name = None
                for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if not delta:
                        continue
                    if delta.tool_calls:
                        tc = delta.tool_calls[0]
                        if tc.id:
                            _tool_call_id = tc.id
                        if tc.function.name:
                            _tool_call_name = tc.function.name
                        frag = tc.function.arguments or ""
                        if frag:
                            args_str += frag
                            if token_cb:
                                try:
                                    token_cb(frag)
                                except Exception:
                                    pass
                    elif delta.content:
                        args_str += delta.content
                        if token_cb:
                            try:
                                token_cb(delta.content)
                            except Exception:
                                pass
                if not args_str:
                    raise RuntimeError("LLM did not return a tool call or content.")
            else:
                stream = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    stream=True,
                )
                args_str = ""
                in_thinking = False
                thinking_buf = ""
                content_buf = ""
                for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        text = delta.content
                        args_str += text
                        # Detect <thinking> and </thinking> tags for reasoning models
                        if "<thinking>" in text:
                            in_thinking = True
                            # Send any accumulated content before <thinking>
                            before = text.split("<thinking>")[0]
                            if before and token_cb:
                                try:
                                    token_cb(before)
                                except Exception:
                                    pass
                            thinking_buf = text.split("<thinking>", 1)[1]
                            continue
                        if "</thinking>" in text:
                            in_thinking = False
                            parts = text.split("</thinking>", 1)
                            thinking_buf += parts[0]
                            # Send accumulated thinking
                            if thinking_cb and thinking_buf:
                                try:
                                    thinking_cb(thinking_buf)
                                except Exception:
                                    pass
                            thinking_buf = ""
                            # Send content after </thinking>
                            if len(parts) > 1 and parts[1] and token_cb:
                                try:
                                    token_cb(parts[1])
                                except Exception:
                                    pass
                            continue
                        if in_thinking:
                            thinking_buf += text
                            # Stream thinking in real-time too
                            if thinking_cb:
                                try:
                                    thinking_cb(text)
                                except Exception:
                                    pass
                        else:
                            if token_cb:
                                try:
                                    token_cb(text)
                                except Exception:
                                    pass

            try:
                parsed = _extract_json(args_str)
                # Defensive unwrapping: If the LLM wrapped the result in {"function_name": {...}} or {"parameters": {...}}
                func_name = tool["function"]["name"]
                if isinstance(parsed, dict):
                    if len(parsed) == 1 and func_name in parsed and isinstance(parsed[func_name], dict):
                        parsed = parsed[func_name]
                    elif len(parsed) == 1 and "parameters" in parsed and isinstance(parsed["parameters"], dict):
                        parsed = parsed["parameters"]
                if not isinstance(parsed, dict):
                    raise ValueError(f"Expected JSON object, got {type(parsed).__name__}: {args_str[:120]}")
                return parsed
            except Exception as e:

                print(f"Attempt {attempt + 1} failed to parse JSON: {args_str[:200]}...")
                last_error = e
                # Add the error to conversation and retry
                if supports_tools:
                    tool_calls = resp.choices[0].message.tool_calls
                    messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
                    messages.append({
                        "role": "tool", 
                        "tool_call_id": tool_calls[0].id,
                        "content": f"JSON解析失败: {str(e)}。请确保所有字符串字段都用双引号括起来，并且JSON格式严格正确。"
                    })
                else:
                    messages.append({"role": "assistant", "content": args_str})
                    messages.append({
                        "role": "user", 
                        "content": f"Validation failed: {str(e)}. Please correct your JSON formatting and try again. Output ONLY raw JSON."
                    })
                continue
        except Exception as e:
            if attempt == retries:
                raise e
            print(f"Attempt {attempt + 1} failed: {str(e)}")
            last_error = e
            continue
            
    raise last_error or RuntimeError("LLM call failed after retries")



