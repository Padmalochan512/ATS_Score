# ATS_Score

## Setup

This app uses Supabase for authentication and persistence.

Required environment variables:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_KEY` for the backend service role key
- `SUPABASE_JWT_SECRET`
- `OWNER_EMAIL` or `OWNER_EMAILS` for the owner dashboard

Database schema:

- Run [`supabase/schema.sql`](/Users/padmalochanmahanta/Desktop/ATS_Score/supabase/schema.sql) in your Supabase SQL editor.

Owner dashboard:

- Sign in with the email configured in `OWNER_EMAIL` / `OWNER_EMAILS`.
- The sidebar will show an `Owner Dashboard` view for that account.
- The dashboard lists recent login events and stored resume text for each saved analysis.
