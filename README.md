# Handbook CSCĐ Service

Backend chatbot service tra cứu *Sổ tay Chiến sĩ Nghĩa vụ CSCĐ* (domain công an, zero-hallucination là P0). Stateless, API-first — website của bạn gọi vào để lấy câu trả lời (stream).

Kiến trúc: full-context (toàn bộ sổ tay ~74k token trong system prompt) + single streaming call. Không retrieval/embedding ở generation. Provider primary = 9Router (Sonnet 4.5 đã validate); tự động failover sang OpenAI-direct khi 9Router lỗi.

## Chạy local

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # điền NINEROUTER_KEY, SERVICE_API_KEY, OPENAI_API_KEY
uvicorn app.main:get_app --factory --host 127.0.0.1 --port 8000
```

Test: `pytest -q` · Lint: `ruff check app/`

## Deploy (Docker)

```bash
cp .env.example .env          # điền key thật trên VPS, KHÔNG commit
docker compose up -d --build
```

Service bind `127.0.0.1:8000` — nginx của bạn terminate TLS rồi proxy vào. KHÔNG phơi cổng này ra internet (không có TLS ở đây).

## Bảo mật

- **Auth:** mọi request (trừ `/v1/health`, `/v1/models`) cần header `X-API-Key: <SERVICE_API_KEY>`. Đây là server-to-server — **backend của website giữ secret**, KHÔNG để lộ ra JS trình duyệt.
- **Không CORS:** service không bật CORS. Trình duyệt không được gọi thẳng (sẽ lộ key) — luôn qua backend của website.
- **Rate limit:** token-bucket theo IP (`RATE_LIMIT_PER_MIN`, mặc định 30) → 429 khi vượt.
- **Validate đầu vào:** `history` (client gửi) bị cap số lượt (`MAX_HISTORY_MSGS`) + độ dài message (`MAX_MESSAGE_CHARS`); role chỉ `user`/`assistant`.

## API contract (`/v1`)

### POST /v1/chat  (SSE)

Request:
```jsonc
{
  "message": "6 điều Bác Hồ dạy CAND là gì?",   // bắt buộc
  "history": [                                    // optional — website tự giữ (stateless)
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "model": "sonnet-4.5"                            // optional, default sonnet-4.5
}
```

Response `text/event-stream`:
```text
event: token   data: {"text":"..."}        # n lần, ghép lại = câu trả lời
event: done    data: {"ttft_s","total_s","tokens_per_s","prompt_tokens",
                      "completion_tokens","cache_read_tokens","provider",
                      "answer","citations":["C171","C172"]}
event: error   data: {"message":"..."}      # nếu upstream lỗi (sau khi đã thử failover)
```

- `citations`: service tự parse mã `[Ck]` trong câu trả lời, kể cả range `[C138-C147]` → enumerate thành `C138..C147`.
- `provider`: `9router` hoặc `openai` — cho biết failover có kích hoạt không.

Ví dụ:
```bash
curl -N -X POST http://127.0.0.1:8000/v1/chat \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $SERVICE_API_KEY" \
  -d '{"message":"6 điều Bác Hồ dạy CAND là gì?"}'
```

### GET /v1/health  (public)
`{status, n_chunks, full_ctx_chars}` — liveness, cho nginx/uptime. Không cần key.

### GET /v1/ready  (public)
`{ready, provider, failover_enabled}` — provider nào đang wired, failover có bật không.

### GET /v1/models  (public)
`{default, models:[...]}` — danh sách model id hợp lệ.

### GET /v1/chunks  (cần key)
`{Ck: {section, section_full, anchors, text}}` — để website render hover trích dẫn.

### GET /v1/metrics  (cần key)
`{total_requests, errors, by_provider, ttft_p50_s, ttft_p95_s}` — theo dõi sức khỏe + tỉ lệ failover.

## Failover & độ tin cậy

- Chỉ tự chuyển provider **trước token đầu tiên**. Nếu primary đứt giữa stream → trả `error` (không vá nửa câu).
- Chỉ failover trên lỗi transient (429/5xx/timeout, và 403-rate-limit của 9Router). Lỗi 400/401/auth thật → fail luôn.
- Circuit breaker: primary fail liên tiếp `BREAKER_THRESHOLD` lần → bỏ qua primary trong `BREAKER_COOLDOWN_S` giây.
- Nếu không cấu hình `OPENAI_API_KEY` → failover tắt, primary lỗi sẽ trả `error`.

## CI/CD

- `ci.yml`: ruff + pytest + docker build trên mọi push/PR.
- `deploy.yml`: SSH vào VPS, `git pull` + `docker compose up -d --build` + curl `/v1/health`. Secrets (`VPS_HOST/USER/SSH_KEY`, `DEPLOY_DIR`) đặt trong GitHub Secrets. Bật branch protection yêu cầu CI xanh trước khi deploy chạy.

## Ghi chú

- Corpus = 173 chunks (170 base `v3_precise_rules` + 3 supplement OCR ảnh: 6 điều Bác Hồ / 5 lời thề / Tư cách CA), copy thẳng vào `data/` — service tự chứa.
- Prompt (`app/core/prompt.py`) bê nguyên si từ demo đã hardened; `tests/test_parity.py` pin byte-for-byte.
- Latency: trên 9Router TTFT ~3-8s (không cache). Muốn ~1s phải dùng provider direct có prompt caching (OpenAI-direct auto-cache khi failover; Anthropic-direct cần thêm adapter).
- Faithfulness guard: cố ý KHÔNG có ở vòng này (quyết định đã chốt). SSE contract chừa sẵn chỗ thêm `guard` event sau mà không phá client.
