# No-Drama Sports Slot (Vercel + Supabase)

## 1) Set up Supabase
1. Create a new Supabase project.
2. Open **SQL Editor**.
3. Run `supabase-schema.sql` from this folder.
4. Go to **Project Settings → API** and copy:
   - Project URL
   - `anon` public key

## 2) Run locally
Because this is a static app, run any static server in this folder:

```bash
cd /Users/racit/.openclaw/workspace/no-drama-sports-slot
python3 -m http.server 8082
```

Open `http://localhost:8082`.
Supabase URL + anon key are already embedded in `index.html` for deploy-ready behavior.

## 3) Deploy to Vercel
1. Push this folder to GitHub.
2. Import repo to Vercel.
3. Deploy as a static project (no build needed).
4. Open live URL — no runtime config input required.

## Notes
- This is hackathon-friendly and intentionally simple.
- Current RLS policies allow public read/write for demo speed.
- For production, add auth and strict policies.
