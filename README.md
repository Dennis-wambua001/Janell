# Jenell Baby's Collection (Stage 2)
1. python -m venv venv && source venv/bin/activate   (Windows: venv\Scripts\activate)
2. pip install -r requirements.txt
3. Set secrets, then run:
   Mac/Linux: export ADMIN_PASSWORD="your-strong-password" SECRET_KEY="long-random-text"
   Windows:   set ADMIN_PASSWORD=your-strong-password  &  set SECRET_KEY=long-random-text
4. python app.py
Store: http://127.0.0.1:5000   Admin: http://127.0.0.1:5000/admin
Set the WhatsApp number: edit the WA constant near the top of the script in static/index.html.
