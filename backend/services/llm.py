import json
import os
import re
from contextvars import ContextVar
from openai import OpenAI
import anthropic as _anthropic_mod
from backend.config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    GLM_API_KEY, GLM_BASE_URL, GLM_MODEL,
    ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL
)

# Providers and models
AVAILABLE_MODELS = [
    "deepseek-chat", "deepseek-reasoner",
    "deepseek-v4-flash", "deepseek-v4-pro",
    "GLM-4.7-Flash", "Kimi-K2.6",
    "astron-code-latest"
]

# Per-request model override (safe for concurrent requests via asyncio context)
_model_var: ContextVar[str] = ContextVar("deepseek_model", default="deepseek-v4-flash")

# Token usage storage for current request
_token_usage_var: ContextVar[dict] = ContextVar("token_usage", default={"input": 0, "output": 0})

# Cache for LLM clients to reuse connection pools
_client_cache = {}

def _get_client_config(selection: str):
    """Return the correct OpenAI client and model name for the given selection."""
    global _client_cache
    
    if selection.startswith("deepseek"):
        cache_key = f"deepseek_{DEEPSEEK_BASE_URL}"
        if cache_key not in _client_cache:
            _client_cache[cache_key] = OpenAI(
                api_key=DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_BASE_URL,
                timeout=120.0,
                max_retries=3
            )
        return _client_cache[cache_key], selection

    elif selection in ["GLM-4.7-Flash", "Kimi-K2.6"]:
        cache_key = f"glm_{GLM_BASE_URL}"
        if cache_key not in _client_cache:
            _client_cache[cache_key] = OpenAI(
                api_key=GLM_API_KEY,
                base_url=GLM_BASE_URL,
                timeout=120.0,
                max_retries=3
            )
        return _client_cache[cache_key], GLM_MODEL if selection == "GLM-4.7-Flash" else selection

    elif selection == "astron-code-latest":
        cache_key = f"astron_{ANTHROPIC_BASE_URL}"
        if cache_key not in _client_cache:
            _client_cache[cache_key] = OpenAI(
                api_key=ANTHROPIC_API_KEY,
                base_url=ANTHROPIC_BASE_URL,
                timeout=120.0,
                max_retries=3
            )
        return _client_cache[cache_key], "astron-code-latest"

    return None, None

def set_model(model: str) -> None:
    if model in AVAILABLE_MODELS:
        _model_var.set(model)

def get_model() -> str:
    return _model_var.get()

def get_token_usage() -> dict:
    return _token_usage_var.get().copy()

def set_token_usage(input_tokens: int, output_tokens: int) -> None:
    _token_usage_var.set({"input": input_tokens, "output": output_tokens})

def _repair_json(s: str) -> str:
    s = s.strip()
    if not s: return s
    
    def quote_val(match):
        val = match.group(1).strip()
        if val.lower() in ["true", "false", "null"]: return f': {val}'
        if val.startswith('"') and val.endswith('"'): return f': {val}'
        try:
            float(val)
            return f': {val}'
        except ValueError: pass
        safe_val = val.replace('"', '\\"')
        return f': "{safe_val}"'

    s = re.sub(r':\s*([^"\[\{\d\-][^,\}]*)', quote_val, s)

    stack = []
    fixed_s = ""
    in_string = False
    escaped = False
    for char in s:
        if char == '"' and not escaped: in_string = not in_string
        if not in_string:
            if char == '{' or char == '[': stack.append('}' if char == '{' else ']')
            elif char == '}' or char == ']':
                if stack and stack[-1] == char: stack.pop()
                else: continue
        fixed_s += char
        escaped = (char == '\\' and not escaped)
    
    while stack: fixed_s += stack.pop()
    return fixed_s

def _extract_json(s: str) -> dict:
    s = s.strip()
    s = re.sub(r'<think>.*?</think>', '', s, flags=re.DOTALL).strip()
    s = re.sub(r'^```json\s*', '', s, flags=re.MULTILINE)
    s = re.sub(r'^```\s*', '', s, flags=re.MULTILINE)
    s = re.sub(r'\s*```$', '', s, flags=re.MULTILINE)
    s = s.strip()

    try: return json.loads(s)
    except json.JSONDecodeError as e:
        if "Extra data" in e.msg:
            try: return json.loads(s[:e.pos])
            except: pass
        try: return json.loads(_repair_json(s))
        except: pass
        
        start, end = s.find('{'), s.rfind('}')
        if start != -1 and end != -1 and end > start:
            candidate = s[start:end+1]
            try: return json.loads(candidate)
            except:
                try: return json.loads(_repair_json(candidate))
                except: pass
        raise e

def _llm_call_anthropic(client, model: str, system: str, user: str, tool: dict, token_cb=None, thinking_cb=None) -> dict:
    func_info = tool["function"]
    tool_name = func_info["name"]
    anthropic_tool = {
        "name": tool_name,
        "description": func_info.get("description", ""),
        "input_schema": func_info.get("parameters", {}),
    }
    messages = [{"role": "user", "content": user}]
    retries = 2
    last_error = None

    for attempt in range(retries + 1):
        try:
            args_str, in_tokens, out_tokens = "", 0, 0
            with client.messages.stream(
                model=model, max_tokens=4096, system=system, messages=messages,
                tools=[anthropic_tool], tool_choice={"type": "tool", "name": tool_name},
            ) as stream:
                for event in stream:
                    if event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            frag = event.delta.text
                            args_str += frag
                            if token_cb: token_cb(frag)
                        elif event.delta.type == "input_json_delta":
                            frag = event.delta.partial_json
                            args_str += frag
                            if token_cb: token_cb(frag)
                        elif event.delta.type == "thinking_delta":
                            if thinking_cb: thinking_cb(event.delta.thinking)
                    elif event.type == "message_start": in_tokens = event.message.usage.input_tokens
                    elif event.type == "message_delta": out_tokens = event.usage.output_tokens

            set_token_usage(in_tokens, out_tokens)
            parsed = _extract_json(args_str)
            if isinstance(parsed, dict) and tool_name in parsed: parsed = parsed[tool_name]
            return parsed
        except Exception as e:
            last_error = e
            messages.append({"role": "assistant", "content": args_str})
            messages.append({"role": "user", "content": f"Fix JSON: {e}"})
    raise last_error

def llm_call(system: str, user: str, tool: dict, token_cb=None, thinking_cb=None, model_override: str = None) -> dict:
    """Single LLM call that enforces a specific function tool and returns parsed args.
    
    token_cb: optional callable(str) called with each streamed token delta (normal content).
    thinking_cb: optional callable(str) called with thinking/reasoning content.
    model_override: Force a specific model for this call (e.g. for fast workers).
    """
    selection = model_override or _model_var.get()
    
    client, model = _get_client_config(selection)
    if not client:
        raise RuntimeError(f"Unsupported model selection: {selection}")

    # ── Anthropic path ──────────────────────────────────────────────────────
    if isinstance(client, _anthropic_mod.Anthropic):
        return _llm_call_anthropic(client, model, system, user, tool, token_cb, thinking_cb)

    # ── OpenAI-compatible path ──────────────────────────────────────────────
    # DeepSeek models and Astron often have issues with tool_choice streaming or strictness.
    # We use JSON mode (Prompt Engineering) for better streaming visibility.
    supports_tools = selection not in [
        "deepseek-chat", "deepseek-reasoner", "deepseek-v4-pro", 
        "deepseek-v4-flash", "astron-code-latest", "Kimi-K2.6"
    ]

    msgs = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]

    if not supports_tools:
        schema_str = json.dumps(tool["function"].get("parameters", {}), ensure_ascii=False)
        msgs[0]["content"] += (
            f"\n\n[重要指令]\n"
            f"你必须输出且仅输出符合以下 JSON Schema 的原始 JSON 对象：\n{schema_str}\n"
            f"不要包含任何 Markdown 代码块（如 ```json）、解释文字或前缀。直接以 '{{' 开始输出。"
        )

    retries = 2
    last_error = None

    for attempt in range(retries + 1):
        try:
            args_str = ""
            input_est = int(len(system + user) * 1.25)
            
            if supports_tools:
                resp = client.chat.completions.create(
                    model=model,
                    messages=msgs,
                    tools=[tool],
                    tool_choice={"type": "function", "function": {"name": tool["function"]["name"]}},
                    stream=True,
                )
                _tool_call_id = None
                # Stream results
                for chunk in resp:
                    if not chunk.choices: continue
                    delta = chunk.choices[0].delta
                    
                    if delta.tool_calls:
                        tc = delta.tool_calls[0]
                        frag = tc.function.arguments or ""
                        if frag:
                            args_str += frag
                            if token_cb:
                                try: token_cb(frag)
                                except: pass
                    elif delta.content:
                        args_str += delta.content
                        if token_cb:
                            try: token_cb(delta.content)
                            except: pass
                if not args_str:
                    raise RuntimeError("LLM did not return a tool call or content.")
            else:
                stream = client.chat.completions.create(
                    model=model,
                    messages=msgs,
                    stream=True,
                )
                in_thinking = False
                for chunk in stream:
                    if not chunk.choices: continue
                    delta = chunk.choices[0].delta
                    
                    # Support for DeepSeek Reasoner's reasoning_content
                    reasoning = getattr(delta, 'reasoning_content', None)
                    if reasoning:
                        if thinking_cb:
                            try: thinking_cb(reasoning)
                            except: pass
                    
                    if delta.content:
                        text = delta.content
                        args_str += text
                        
                        if "<thinking>" in text:
                            in_thinking = True
                            continue
                        if "</thinking>" in text:
                            in_thinking = False
                            continue
                        
                        if in_thinking:
                            if thinking_cb:
                                try: thinking_cb(text)
                                except: pass
                        else:
                            if token_cb:
                                try: token_cb(text)
                                except: pass

            try:
                parsed = _extract_json(args_str)
                # Defensive unwrapping
                func_name = tool["function"]["name"]
                if isinstance(parsed, dict):
                    if len(parsed) == 1 and func_name in parsed and isinstance(parsed[func_name], dict):
                        parsed = parsed[func_name]
                    elif len(parsed) == 1 and "parameters" in parsed and isinstance(parsed["parameters"], dict):
                        parsed = parsed["parameters"]
                if not isinstance(parsed, dict):
                    raise ValueError(f"Expected JSON object, got {type(parsed).__name__}")
                
                # Final token update
                set_token_usage(input_est, int(len(args_str) * 1.25))
                return parsed
            except Exception as e:
                print(f"Attempt {attempt + 1} failed to parse JSON: {args_str[:200]}...")
                last_error = e
                msgs.append({"role": "assistant", "content": args_str})
                msgs.append({
                    "role": "user", 
                    "content": f"Validation failed: {str(e)}. Please correct your JSON formatting and try again. Output ONLY the raw properties object as JSON."
                })
                continue
        except Exception as e:
            if attempt == retries:
                raise e
            print(f"Attempt {attempt + 1} failed: {str(e)}")
            last_error = e
            continue
            
    raise last_error or RuntimeError("LLM call failed after retries")
