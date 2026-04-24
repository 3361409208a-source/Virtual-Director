import json
from contextvars import ContextVar
from openai import OpenAI
from backend.config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    GLM_API_KEY, GLM_BASE_URL, GLM_MODEL
)


# Providers and models
AVAILABLE_MODELS = ["deepseek-chat", "deepseek-reasoner", "glm-4-flash"]

# Per-request model override (safe for concurrent requests via asyncio context)
_model_var: ContextVar[str] = ContextVar("deepseek_model", default=DEEPSEEK_MODEL)


def _get_client_config(model: str):
    """Return the correct OpenAI client and model name for the given selection."""
    if model.startswith("deepseek"):
        return OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            timeout=120.0,
            max_retries=3
        ), model
    elif model == "glm-4-flash":
        return OpenAI(
            api_key=GLM_API_KEY,
            base_url=GLM_BASE_URL,
            timeout=120.0,
            max_retries=3
        ), GLM_MODEL
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




def llm_call(system: str, user: str, tool: dict) -> dict:
    """Single LLM call that enforces a specific function tool and returns parsed args."""
    selection = _model_var.get()
    
    # Provider-specific fallbacks
    if selection == "deepseek-reasoner":
        print(f"⚠️ {selection} 不支持工具调用，已自动切换至 deepseek-chat 完成结构化任务")
        selection = "deepseek-chat"

    client, model = _get_client_config(selection)
    if not client:
        raise RuntimeError(f"Unsupported model selection: {selection}")

    retries = 2
    last_error = None
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]

    for attempt in range(retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=[tool],
                tool_choice={"type": "function", "function": {"name": tool["function"]["name"]}},
            )

            
            tool_calls = resp.choices[0].message.tool_calls
            if not tool_calls:
                content = resp.choices[0].message.content
                if content:
                    try:
                        return _extract_json(content)
                    except Exception:
                        pass
                raise RuntimeError(f"LLM did not return a tool call. Content: {content}")

            args_str = tool_calls[0].function.arguments
            try:
                return _extract_json(args_str)
            except Exception as e:
                print(f"Attempt {attempt + 1} failed to parse JSON: {args_str[:200]}...")
                last_error = e
                # Add the error to conversation and retry
                messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
                messages.append({
                    "role": "tool", 
                    "tool_call_id": tool_calls[0].id,
                    "content": f"JSON解析失败: {str(e)}。请确保所有字符串字段都用双引号括起来，并且JSON格式严格正确。"
                })
                continue
        except Exception as e:
            if attempt == retries:
                raise e
            print(f"Attempt {attempt + 1} failed: {str(e)}")
            last_error = e
            continue
            
    raise last_error or RuntimeError("LLM call failed after retries")



