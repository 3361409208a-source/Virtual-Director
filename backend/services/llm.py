import json
from contextvars import ContextVar
from openai import OpenAI
from backend.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL,
    timeout=120.0,  # Increase timeout for reasoning models
    max_retries=3,  # Add retries for transient connection errors
)


AVAILABLE_MODELS = ["deepseek-chat", "deepseek-reasoner"]

# Per-request model override (safe for concurrent requests via asyncio context)
_model_var: ContextVar[str] = ContextVar("deepseek_model", default=DEEPSEEK_MODEL)


def set_model(model: str) -> None:
    """Set the DeepSeek model for the current request context."""
    if model in AVAILABLE_MODELS:
        _model_var.set(model)


def get_model() -> str:
    return _model_var.get()


def _repair_json(s: str) -> str:
    """Attempt to fix common LLM JSON errors like missing or extra closing brackets."""
    s = s.strip()
    if not s:
        return s
    
    # 1. Basic balancing: count { vs } and [ vs ]
    # This is a naive approach but often works for trailing garbage or missing closings
    stack = []
    fixed_s = ""
    for i, char in enumerate(s):
        if char == '{' or char == '[':
            stack.append('}' if char == '{' else ']')
        elif char == '}' or char == ']':
            if stack and stack[-1] == char:
                stack.pop()
            else:
                # Mismatched or extra closing, skip it or handle it
                continue
        fixed_s += char
    
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
    model = _model_var.get()

    # DeepSeek R1 (reasoner) does not support tool calling in the official API.
    # Fallback to deepseek-chat (V3) for structured tool-based tasks.
    if model == "deepseek-reasoner":
        print(f"⚠️ {model} 不支持工具调用，已自动切换至 deepseek-chat 完成结构化任务")
        model = "deepseek-chat"

    try:

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": tool["function"]["name"]}},
        )
    except Exception as e:
        error_msg = str(e)
        if "Connection error" in error_msg or "APIConnectionError" in error_msg:
            print(f"网络连接失败，请检查代理设置或 api.deepseek.com 的连通性。错误: {error_msg}")
            raise RuntimeError(f"DeepSeek API 连接失败。如果您在境内，请确保开启了全局代理，或者尝试切换到 deepseek-chat 模型。详情: {error_msg}")
        raise e

    tool_calls = resp.choices[0].message.tool_calls

    if not tool_calls:
        # Fallback: some models might put JSON in content if tool_choice is ignored
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
        print(f"Failed to parse LLM response: {args_str}")
        raise e


