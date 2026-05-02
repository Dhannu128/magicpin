# Deploy guide — pick one path

## Option A: Render (recommended, free tier, ~5 min)

### A1. Render with GitHub auto-deploy

```powershell
cd D:\personal\AI-ML\hackathon\Magicpin\magicpin-ai-challenge
git init
git add .
git commit -m "vera bot v1.0"
git branch -M main
gh repo create vera-bot --public --source . --push     # needs `gh auth login` once
```

Then on https://render.com:
1. New → Web Service → "Connect GitHub" → pick `vera-bot`.
2. Render auto-detects Dockerfile.
3. Add env vars from `deploy/render.yaml` (Render only reads `render.yaml` if blueprints are enabled — easier to just paste).
4. **Set `LLM_API_KEY`** in the dashboard (don't commit it).
5. Click Create → wait ~3 min for build → URL like `https://vera-bot.onrender.com`.

### A2. Render manual zip (no GitHub)

```powershell
Compress-Archive -Path bot, dataset, judge_simulator.py, Dockerfile, requirements.txt, README.md -DestinationPath vera-bot.zip
```

On Render: New → Web Service → "Public Git repository" doesn't work for zip; use Render's "Deploy from a private repository or upload" option (paid plans only). For free tier, GitHub or Bitbucket only — use A1 instead, or A3.

## Option B: Fly.io (Mumbai region, ~10 min)

```powershell
# Once: install flyctl
iwr https://fly.io/install.ps1 -useb | iex

# Then:
flyctl auth signup       # or `flyctl auth login` if you already have an account
cd D:\personal\AI-ML\hackathon\Magicpin\magicpin-ai-challenge
Copy-Item deploy\fly.toml .\
flyctl launch --no-deploy --copy-config
flyctl secrets set LLM_API_KEY=sk-m0QVS0x3V4avRJMbQjT8kbzSQRHjEUrVYvJ33iCDBCdPjPLw
flyctl deploy
flyctl status                                        # prints your https URL
```

Cost: free for the small machine (256-512 MB shared CPU). Card required to sign up but won't be charged.

## Option C: Railway (~5 min)

```powershell
# Once: install Railway CLI
npm i -g @railway/cli
railway login
cd D:\personal\AI-ML\hackathon\Magicpin\magicpin-ai-challenge
railway init
railway up
railway variables set LLM_API_KEY=...    # set the rest from .env.example
railway domain                            # creates a public URL
```

Cost: $5/mo after $5 trial credit.

## Option D: Local + ngrok tunnel (free, no signup, but laptop must stay on)

```powershell
# Once: install ngrok and `ngrok config add-authtoken YOUR_TOKEN`  (free at ngrok.com)
cd D:\personal\AI-ML\hackathon\Magicpin\magicpin-ai-challenge
.\.venv\Scripts\python.exe -m uvicorn bot.main:app --host 0.0.0.0 --port 8080 &
ngrok http 8080
```

Public URL: the `https://*.ngrok-free.app` URL ngrok prints. Submit that.

## Post-deploy verification (run from any machine)

```bash
export BOT_URL=https://your-deployed-bot.example.com
curl $BOT_URL/v1/healthz
curl $BOT_URL/v1/metadata
curl -X POST -H "Content-Type: application/json" \
  -d '{"scope":"category","context_id":"dentists","version":1,"payload":{"slug":"dentists","voice":{"tone":"peer_clinical","vocab_taboo":["guaranteed"]}},"delivered_at":"2026-04-26T00:00:00Z"}' \
  $BOT_URL/v1/context
curl -X POST -H "Content-Type: application/json" \
  -d '{"now":"2026-04-26T10:35:00Z","available_triggers":[]}' \
  $BOT_URL/v1/tick
```

All four commands should return 200s with the schemas in `examples/api-call-examples.md`.

## Re-run judge_simulator against the public URL

```powershell
cd D:\personal\AI-ML\hackathon\Magicpin\magicpin-ai-challenge
$env:LLM_API_KEY = "sk-..."
$env:LLM_BASE_URL = "https://api.tokenrouter.com/v1"
$env:JUDGE_MODEL = "anthropic/claude-opus-4.7"
$env:BOT_URL = "https://your-deployed-bot.example.com"
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe run_judge.py full_evaluation
```

Expect ~39-40 mean per `parse_scores.py`, with 13 messages scored.
