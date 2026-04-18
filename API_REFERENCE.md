# vLLM OpenAI-Compatible API Reference

**Server**: `http://localhost:30000`
**Base URL**: `http://localhost:30000/v1`
**Model**: `Qwen/Qwen3.6-35B-A3B-FP8`
**Max Model Length**: 262,144 tokens
**Last Validated**: 2026-04-18

---

## Authentication

vLLM supports optional API key authentication via the `--api-key` server flag.

```bash
vllm serve Qwen/Qwen3.6-35B-A3B-FP8 --api-key token-abc123
```

When configured, include the key in requests:

```bash
curl -H "Authorization: Bearer token-abc123" http://localhost:30000/v1/models
```

Without `--api-key`, no authentication is required.

---

## Supported APIs

| API | Endpoint | Method | Applicable Models |
|-----|----------|--------|-------------------|
| Chat Completions | `/v1/chat/completions` | POST | Text generation models with chat template |
| Completions | `/v1/completions` | POST | Text generation models |
| Responses | `/v1/responses` | POST | Text generation models |
| Embeddings | `/v1/embeddings` | POST | Embedding/pooling models |
| Transcriptions | `/v1/audio/transcriptions` | POST | ASR models (Whisper) |
| Translations | `/v1/audio/translations` | POST | ASR models (Whisper) |
| Realtime | `/v1/realtime` | POST | ASR models |
| Tokenize | `/tokenize` | POST | Any model with tokenizer |
| Detokenize | `/detokenize` | POST | Any model with tokenizer |

---

## 1. List Models

**GET** `/v1/models`

Returns available models.

### Example

```bash
curl http://localhost:30000/v1/models
```

### Response (validated)

```json
{
  "object": "list",
  "data": [
    {
      "id": "Qwen/Qwen3.6-35B-A3B-FP8",
      "object": "model",
      "created": 1776463288,
      "owned_by": "vllm",
      "root": "Qwen/Qwen3.6-35B-A3B-FP8",
      "parent": null,
      "max_model_len": 262144,
      "permission": [
        {
          "id": "modelperm-...",
          "object": "model_permission",
          "created": 1776463288,
          "allow_create_engine": false,
          "allow_sampling": true,
          "allow_logprobs": true,
          "allow_view": true
        }
      ]
    }
  ]
}
```

---

## 2. Chat Completions

**POST** `/v1/chat/completions`

Creates a model response for the given chat conversation.

### Request Body

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | Yes | Model ID (e.g., `Qwen/Qwen3.6-35B-A3B-FP8`) |
| `messages` | array | Yes | Conversation messages |
| `max_tokens` | integer | No | Max output tokens |
| `temperature` | number | No | Sampling temperature (0-2) |
| `top_p` | number | No | Nucleus sampling threshold |
| `n` | integer | No | Number of completions (default: 1) |
| `stream` | boolean | No | Enable SSE streaming (default: false) |
| `stop` | string|array | No | Stop sequences |
| `frequency_penalty` | number | No | -2.0 to 2.0 |
| `presence_penalty` | number | No | -2.0 to 2.0 |
| `logprobs` | boolean | No | Return log probabilities |
| `top_logprobs` | integer | No | 0-20, requires `logprobs: true` |
| `response_format` | object | No | `{"type": "json_object"}` or `{"type": "text"}` |
| `tools` | array | No | Tool definitions for function calling |
| `tool_choice` | string/object | No | `"auto"`, `"none"`, `"required"`, or specific tool |
| `parallel_tool_calls` | boolean | No | Allow multiple tool calls (default: true) |

### vLLM-Specific Parameters (via `extra_body` or direct JSON)

| Parameter | Type | Description |
|-----------|------|-------------|
| `top_k` | integer | Top-k sampling |
| `min_p` | number | Min-p sampling (conflicts with speculative decoding) |
| `repetition_penalty` | number | Repetition penalty |
| `use_beam_search` | boolean | Beam search (default: false) |
| `ignore_eos` | boolean | Ignore EOS tokens |
| `stop_token_ids` | array | Custom stop token IDs |
| `skip_special_tokens` | boolean | Skip special tokens (default: true) |
| `return_tokens_as_token_ids` | boolean | Return tokens as `token_id:{id}` strings |
| `return_token_ids` | boolean | Include token IDs in output |
| `echo` | boolean | Prepend last message if same role |
| `add_generation_prompt` | boolean | Add gen prompt to chat template (default: true) |
| `continue_final_message` | boolean | Continue final message without EOS |
| `add_special_tokens` | boolean | Add BOS tokens on top of chat template (default: false) |
| `documents` | array | RAG documents `[{title, text}]` |
| `structured_outputs` | object | Constrained decoding / structured outputs |
| `priority` | integer | Request priority (lower = earlier) |
| `request_id` | string | Custom request ID |
| `cache_salt` | string | Cache salt for privacy |
| `bad_words` | array | Words to exclude from output |
| `repetition_detection` | object | Detect repetitive N-gram patterns |

### Message Format

```json
{
  "role": "user|assistant|system|developer|tool|function",
  "content": "string or [{type, text}]"
}
```

Roles: `developer`, `system`, `user`, `assistant`, `tool`, `function`.

### Streaming Response Format

When `stream: true`, responses are Server-Sent Events:

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":...,"model":"...","choices":[{"index":0,"delta":{"role":"assistant","content":""},"logprobs":null,"finish_reason":null}]}
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":...,"model":"...","choices":[{"index":0,"delta":{"reasoning":"Here"},"logprobs":null,"finish_reason":null,"token_ids":null}]}
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":...,"model":"...","choices":[{"index":0,"delta":{},"logprobs":null,"finish_reason":"stop"}]}
```

**NOTE**: The `reasoning` field appears in streaming deltas for this model (contains the thinking process). The `content` field may be `null` when reasoning is generated.

### Response Format (validated)

```json
{
  "id": "chatcmpl-b1c0c9106ac52521",
  "object": "chat.completion",
  "created": 1776463291,
  "model": "Qwen/Qwen3.6-35B-A3B-FP8",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": null,
        "reasoning": "Here's a thinking process:\n\n1.  **Analyze...",
        "refusal": null,
        "annotations": null,
        "audio": null,
        "function_call": null,
        "tool_calls": []
      },
      "logprobs": {...},
      "finish_reason": "stop|length|tool_calls|content_filter",
      "stop_reason": null
    }
  ],
  "usage": {
    "prompt_tokens": 16,
    "completion_tokens": 20,
    "total_tokens": 36
  },
  "system_fingerprint": null,
  "prompt_logprobs": null,
  "prompt_token_ids": null,
  "kv_transfer_params": null
}
```

### Key Deviations from OpenAI Spec

| Field | vLLM Behavior | Notes |
|-------|---------------|-------|
| `message.content` | Can be `null` | When model generates reasoning, content goes to `reasoning` field |
| `message.reasoning` | **vLLM extension** | Contains thinking/reasoning text (not in OpenAI spec) |
| `choices[].stop_reason` | **vLLM extension** | Additional field alongside `finish_reason` |
| `choices[].token_ids` | **vLLM extension** | Token IDs in choices when `return_token_ids` is set |
| `prompt_logprobs` | **vLLM extension** | Log probs for prompt tokens |
| `prompt_token_ids` | **vLLM extension** | Input token IDs in response |
| `kv_transfer_params` | **vLLM extension** | KV transfer params in response |
| `stream delta.reasoning` | **vLLM extension** | Reasoning text streamed in delta |
| `imageurl.detail` | **Ignored** | Parameter accepted but not used |
| `user` parameter | **Ignored** | Accepted but has no effect |

### Example: Basic Chat

```bash
curl http://localhost:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.6-35B-A3B-FP8",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Hello!"}
    ],
    "max_tokens": 100
  }'
```

### Example: Streaming

```bash
curl http://localhost:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.6-35B-A3B-FP8",
    "messages": [{"role": "user", "content": "Say hi"}],
    "max_tokens": 50,
    "stream": true
  }'
```

### Example: Logprobs

```bash
curl http://localhost:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.6-35B-A3B-FP8",
    "messages": [{"role": "user", "content": "Say hi"}],
    "max_tokens": 10,
    "logprobs": true,
    "top_logprobs": 2
  }'
```

Logprobs response structure:

```json
"logprobs": {
  "content": [
    {
      "token": "Here",
      "logprob": -0.181,
      "bytes": [72, 101, 114, 101],
      "top_logprobs": [
        {"token": "Here", "logprob": -0.181, "bytes": [72, 101, 114, 101]},
        {"token": "Thinking", "logprob": -1.806, "bytes": [84, 104, 105, 110, 107, 105, 110, 103]}
      ]
    }
  ]
}
```

### Example: vLLM Extra Params (Python client)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:30000/v1",
    api_key="token-abc123"  # omit if no API key configured
)

completion = client.chat.completions.create(
    model="Qwen/Qwen3.6-35B-A3B-FP8",
    messages=[{"role": "user", "content": "Classify sentiment: vLLM is great!"}],
    max_tokens=100,
    extra_body={
        "top_k": 50,
        "repetition_penalty": 1.1,
        "structured_outputs": {"choice": ["positive", "negative"]},
    }
)
```

### Example: JSON Response Format

```bash
curl http://localhost:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.6-35B-A3B-FP8",
    "messages": [{"role": "user", "content": "Respond with JSON: {\"answer\": 42}"}],
    "max_tokens": 50,
    "response_format": {"type": "json_object"}
  }'
```

### Example: Tool Calling

```bash
curl http://localhost:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.6-35B-A3B-FP8",
    "messages": [{"role": "user", "content": "What is the weather in Tokyo?"}],
    "max_tokens": 200,
    "tools": [{
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get the current weather for a location",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string", "description": "City and state"}
          },
          "required": ["location"]
        }
      }
    }],
    "tool_choice": "auto"
  }'
```

---

## 3. Completions (Legacy)

**POST** `/v1/completions`

Creates a text completion (legacy endpoint).

### Request Body

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | Yes | Model ID |
| `prompt` | string | Yes | Input text prompt |
| `max_tokens` | integer | No | Max output tokens |
| `temperature` | number | No | Sampling temperature |
| `top_p` | number | No | Nucleus sampling |
| `n` | integer | No | Number of completions |
| `stream` | boolean | No | Enable streaming |
| `stop` | string|array | No | Stop sequences |
| `logprobs` | integer | No | Return top N log probs |
| `suffix` | string | No | **Not supported** by vLLM |

### vLLM-Specific Extra Params

Same as Chat Completions plus:
- `prompt_embeds`: Pre-computed prompt embeddings
- `response_format`: `{"type": "json_object"}`, `{"type": "structural_tag"}`, or `{"type": "text"}`
- `allowed_token_ids`: Restrict output to specific token IDs

### Response (validated)

```json
{
  "id": "cmpl-8e358270ff6be9d0",
  "object": "text_completion",
  "created": 1776463293,
  "model": "Qwen/Qwen3.6-35B-A3B-FP8",
  "choices": [
    {
      "index": 0,
      "text": "\n\n<think>\nHere's a thinking process...",
      "logprobs": null,
      "finish_reason": "stop|length",
      "stop_reason": null,
      "token_ids": null
    }
  ],
  "usage": {
    "prompt_tokens": 6,
    "completion_tokens": 20,
    "total_tokens": 26
  }
}
```

---

## 4. Responses API

**POST** `/v1/responses`

Newer API compatible with OpenAI's Responses endpoint.

### Request Body

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | Yes | Model ID |
| `input` | array | Yes | Input messages |
| `max_output_tokens` | integer | No | Max output tokens |
| `temperature` | number | No | Sampling temperature |
| `top_p` | number | No | Nucleus sampling |
| `tools` | array | No | Tool definitions |
| `tool_choice` | string | No | `"auto"`, `"none"`, `"required"` |
| `parallel_tool_calls` | boolean | No | Allow parallel tool calls |
| `max_tool_calls` | integer | No | Max tool calls per response |
| `previous_response_id` | string | No | Resume conversation |
| `background` | boolean | No | Async processing |
| `truncation` | string | No | `"disabled"` or `"auto"` |
| `prompt` | object | No | Custom prompt |
| `metadata` | object | No | Key-value metadata |

### vLLM-Specific Extra Params

- `request_id`: Custom request ID
- `media_io_kwargs`: Media IO connector kwargs
- `mm_processor_kwargs`: Multi-modal processor kwargs
- `priority`: Request priority
- `cache_salt`: Cache salt
- `enable_response_messages`: Include input/output messages
- `previous_input_messages`: Harmony-format previous messages
- `structured_outputs`: Constrained decoding params

### Response (validated)

```json
{
  "id": "resp_a3e9670c4e6ebc44",
  "created_at": 1776463313,
  "model": "Qwen/Qwen3.6-35B-A3B-FP8",
  "object": "response",
  "status": "completed",
  "output": [
    {
      "id": "rs_b0625acae3efdfe5",
      "type": "reasoning",
      "content": [{"text": "Here's a thinking process...", "type": "reasoning_text"}]
    },
    {
      "id": "msg_8bb778a0415755ee",
      "type": "message",
      "role": "assistant",
      "status": "completed",
      "content": [
        {"type": "output_text", "text": "\n\nHi! 👋 How can I help you today?", "annotations": []}
      ]
    }
  ],
  "usage": {
    "input_tokens": 12,
    "output_tokens": 173,
    "total_tokens": 185,
    "input_tokens_details": {
      "cached_tokens": 0,
      "input_tokens_per_turn": [],
      "cached_tokens_per_turn": []
    },
    "output_tokens_details": {
      "reasoning_tokens": 0,
      "tool_output_tokens": 0,
      "output_tokens_per_turn": [],
      "tool_output_tokens_per_turn": []
    }
  }
}
```

---

## 5. Tokenize / Detokenize

### Tokenize

**POST** `/tokenize`

Tokenizes input text.

#### Request

```json
{
  "model": "Qwen/Qwen3.6-35B-A3B-FP8",
  "prompt": "Hello world"
}
```

#### Response (validated)

```json
{
  "count": 2,
  "max_model_len": 262144,
  "tokens": [9419, 1814],
  "token_strs": null
}
```

### Detokenize

**POST** `/detokenize`

Detokenizes token IDs back to text.

#### Request

```json
{
  "model": "Qwen/Qwen3.6-35B-A3B-FP8",
  "tokens": [9419, 1814]
}
```

#### Response

```json
{
  "text": "Hello world"
}
```

---

## 6. Error Handling

All errors follow OpenAI-compatible error format:

```json
{
  "error": {
    "message": "Detailed error message",
    "type": "NotFoundError|BadRequestError|InternalServerError",
    "param": "field_name_or_null",
    "code": 404
  }
}
```

### Common Errors

| Status | Code | Type | When |
|--------|------|------|------|
| 404 | 404 | NotFoundError | Model does not exist |
| 400 | 400 | BadRequestError | Invalid parameters (e.g., `min_p` with speculative decoding) |
| 500 | 500 | InternalServerError | Server-side error |

### Example: Model Not Found

```json
{
  "error": {
    "message": "The model `nonexistent-model` does not exist.",
    "type": "NotFoundError",
    "param": "model",
    "code": 404
  }
}
```

### Example: Unsupported Parameter Combination

```json
{
  "error": {
    "message": "The min_p and logit_bias sampling parameters are not yet supported with speculative decoding.",
    "type": "BadRequestError",
    "param": null,
    "code": 400
  }
}
```

---

## 7. Known Quirks & Deviations

### Reasoning Output

This model (Qwen3.6-35B-A3B-FP8) generates extensive reasoning/thinking output. The `reasoning` field in responses contains the thinking process, while `content` may be `null` or contain minimal text. This affects:
- Token counts: reasoning tokens consume `completion_tokens`
- Streaming: reasoning appears in `delta.reasoning`, not `delta.content`
- JSON mode: model may output reasoning before JSON, breaking strict JSON parsing
- Tool calls: reasoning tokens may exhaust `max_tokens` before tool calls are generated

### Parameter Limitations

| Parameter | Behavior |
|-----------|----------|
| `min_p` | Conflicts with speculative decoding (400 error) |
| `logit_bias` | Conflicts with speculative decoding (400 error) |
| `suffix` | Not supported in Completions API |
| `imageurl.detail` | Accepted but ignored |
| `user` | Accepted but ignored in Chat Completions |
| `parallel_tool_calls: false` | Ensures 0 or 1 tool call per request |
| `parallel_tool_calls: true` | Allows multiple tool calls (model-dependent) |

### Response Fields

Fields present in vLLM responses but NOT in OpenAI spec:
- `message.reasoning` - Thinking/reasoning text
- `choices[].stop_reason` - Alternative to `finish_reason`
- `choices[].token_ids` - Token IDs per choice
- `prompt_logprobs` - Prompt token log probabilities
- `prompt_token_ids` - Input token IDs
- `kv_transfer_params` - KV transfer info
- `service_tier` - May be `null`
- `system_fingerprint` - May be `null`

### Chat Template

The model requires a chat template in its tokenizer. Without one, all chat requests will error. vLLM auto-detects content format:
- `"string"` - Plain text content (most models)
- `"openai"` - Array of content parts with `type`/`text` fields (newer models)

Override with `--chat-template-content-format` CLI argument.

### Generation Config

vLLM applies `generation_config.json` from the model repository by default, which may override sampling parameter defaults. Disable with `--generation-config vllm` server flag.

---

## 8. Python Client Example

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:30000/v1",
    api_key="token-abc123"  # omit if no API key
)

# Basic chat
response = client.chat.completions.create(
    model="Qwen/Qwen3.6-35B-A3B-FP8",
    messages=[{"role": "user", "content": "Hello!"}],
    max_tokens=100,
)
print(response.choices[0].message.content)
print(response.choices[0].message.reasoning)  # vLLM extension

# Streaming
for chunk in client.chat.completions.create(
    model="Qwen/Qwen3.6-35B-A3B-FP8",
    messages=[{"role": "user", "content": "Count to 5"}],
    max_tokens=50,
    stream=True,
):
    for choice in chunk.choices:
        print(choice.delta.content or choice.delta.reasoning or "", end="")

# Extra vLLM parameters
response = client.chat.completions.create(
    model="Qwen/Qwen3.6-35B-A3B-FP8",
    messages=[{"role": "user", "content": "Classify: vLLM is amazing!"}],
    max_tokens=10,
    extra_body={
        "top_k": 50,
        "repetition_penalty": 1.1,
    },
)

# Completions API
response = client.completions.create(
    model="Qwen/Qwen3.6-35B-A3B-FP8",
    prompt="Once upon a time",
    max_tokens=50,
)
print(response.choices[0].text)

# Tokenize
tokenized = client.post("/tokenize", json={
    "model": "Qwen/Qwen3.6-35B-A3B-FP8",
    "prompt": "Hello world",
})
print(tokenized)  # {"count": 2, "tokens": [9419, 1814]}

# Responses API
response = client.responses.create(
    model="Qwen/Qwen3.6-35B-A3B-FP8",
    input=[{"role": "user", "content": "Hello!"}],
)
for item in response.output:
    if item.type == "message":
        for content in item.content:
            if content.type == "output_text":
                print(content.text)
```

---

## 9. HTTP Headers

| Header | Description |
|--------|-------------|
| `Content-Type: application/json` | Required for POST bodies |
| `Authorization: Bearer <key>` | When API key is configured |
| `X-Request-Id` | Custom request ID (requires `--enable-request-id-headers`) |

---

## 10. Model Information

| Property | Value |
|----------|-------|
| Model ID | `Qwen/Qwen3.6-35B-A3B-FP8` |
| Owned by | `vllm` |
| Max context length | 262,144 tokens |
| Quantization | FP8 |
| Architecture | MoE (Mixture of Experts) - 35B total, 3B active |
| Reasoning | Generates thinking/reasoning output by default |
