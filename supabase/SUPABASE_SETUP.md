# Supabase setup (Roman Urdu)

1. https://supabase.com par free account banayein -> **New project** (naam: jarvis-ai, password yaad rakhein).
2. Project tayyar hone ke baad: **SQL Editor -> New query**. `supabase/schema.sql` ka poora content copy karke paste karein aur **Run** dabayein.
3. **Project Settings -> API** se do cheezein copy karein:
   - **Project URL**  -> `SUPABASE_URL`
   - **anon public** key -> `SUPABASE_ANON_KEY`
   (**service_role** key kabhi use na karein. App usay reject kar degi.)
4. `JARVIS_AI\.env` file kholein aur ye do lines bharein:
   ```
   SUPABASE_URL=https://xxxxxxxx.supabase.co
   SUPABASE_ANON_KEY=eyJ...
   ```
5. (Optional, testing ke liye) **Authentication -> Providers -> Email** mein "Confirm email" band kar dein, to signup ke foran baad login ho jayega. Agar on rakhein to signup ke baad email ka link click karna hoga.
6. Backend dobara chalayein: `.\run_backend.ps1`
