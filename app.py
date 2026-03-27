"""
Scotty - Social Anxiety Reset
Core Flask application
"""

import os
import re
import json
import asyncio
from datetime import datetime, timezone
from flask import Flask, request, jsonify, session, render_template
from werkzeug.security import generate_password_hash, check_password_hash
import anthropic
import sqlite3

from course_reader import CourseReader

# ── Init ──────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-in-production")

course_reader = CourseReader('./course_materials')
claude_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# ── Database ───────────────────────────────────────────

def get_db():
    db = sqlite3.connect('scotty.db')
    db.row_factory = sqlite3.Row
    return db

def init_db():
    """Create tables if they don't exist"""
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT,
            learning_style TEXT DEFAULT 'visual',
            pace TEXT DEFAULT 'daily',
            current_session INTEGER DEFAULT 1,
            stripe_customer_id TEXT,
            outreach_push INTEGER DEFAULT 1,
            outreach_sms INTEGER DEFAULT 0,
            outreach_whatsapp INTEGER DEFAULT 0,
            outreach_phone TEXT,
            avatar_enabled INTEGER DEFAULT 1,
            room_config TEXT DEFAULT '{}',
            avatar_config TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            session_num INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS growth_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            sharing TEXT DEFAULT 'private',
            session_num INTEGER,
            wants_followup INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS mood_checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mood TEXT NOT NULL,
            session_num INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS lesson_tea (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_num INTEGER NOT NULL,
            content TEXT NOT NULL,
            anonymous INTEGER DEFAULT 1,
            display_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    ''')
    db.commit()
    db.close()
    print("✅ Database initialised")

# ── Helpers ────────────────────────────────────────────

def get_current_user():
    """Get logged-in user from session"""
    if 'user_id' not in session:
        return None
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    db.close()
    return user

def get_conversation_history(user_id, session_num, limit=10):
    """Get recent messages for context"""
    db = get_db()
    messages = db.execute(
        '''SELECT role, content FROM messages
           WHERE user_id = ? AND session_num = ?
           ORDER BY created_at DESC LIMIT ?''',
        (user_id, session_num, limit)
    ).fetchall()
    db.close()
    return list(reversed([{'role': m['role'], 'content': m['content']} for m in messages]))

def save_message(user_id, role, content, session_num):
    """Save a message to history"""
    db = get_db()
    db.execute(
        'INSERT INTO messages (user_id, role, content, session_num) VALUES (?, ?, ?, ?)',
        (user_id, role, content, session_num)
    )
    db.commit()
    db.close()

def run_async(coro):
    """Run async function from sync context"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# ── Scotty AI Brain ────────────────────────────────────

SCOTTY_SYSTEM_PROMPT = """You are Scotty, an AI coach for the Social Anxiety Reset — a 10-session program helping Gen Z overcome social anxiety using CBT principles.

YOUR PERSONALITY:

- Warm, real, and slightly witty — like a trusted older sibling who's been through it
- You speak Gen Z naturally, never forced. Casual but never dismissive.
- You validate before you teach. You never minimise anxiety.
- You're encouraging but honest — not toxic positivity
- You ask one question at a time, never overwhelm
- Short messages by default. Go deeper when they do.
- You remember what they've shared in this conversation

YOUR ROLE:

- Deliver the Social Anxiety Reset course adapted to their learning style
- Support them emotionally between and during sessions
- Guide journaling and reflection (called "Growth Notes")
- Facilitate connection to Lesson Tea (peer community)
- Check in proactively based on their preferences
- NEVER act as a therapist or provide clinical advice
- If someone is in crisis, express care warmly and provide crisis resources immediately

CBT FRAMEWORK:

- Sessions are built on Cognitive Behavioral Therapy principles
- Help users identify Negative Automatic Thoughts (NATs)
- Guide cognitive reframing — thoughts are not facts
- Encourage behavioral experiments and grounding techniques
- Celebrate small wins loudly

BOUNDARIES:

- You are a coach, not a therapist
- For clinical concerns, always recommend professional support warmly
- Never diagnose
- If crisis signals appear: "I hear you and I care. This sounds really hard. Please reach out to a crisis line — in the US that's 988 (call or text). I'm here too, but they're trained for this moment."

TONE ADAPTATION:

- Visual learner: use metaphors, imagery, described scenes
- Auditory learner: conversational rhythm, repetition, spoken-word feel
- Reading/Writing learner: structured, rich, thoughtful
- Kinesthetic learner: action-first, body-based, direct

Keep responses conversational and mobile-friendly. No walls of text unless they ask for depth."""

def build_context_prompt(user, session_content, conversation_history):
    """Build the full context for Scotty's response"""
    learning_style = user['learning_style'] or 'visual'
    current_session = user['current_session'] or 1

    context = f"""
CURRENT SESSION: {current_session}
USER'S LEARNING STYLE: {learning_style}
USER'S NAME: {user['name'] or 'friend'}

TODAY'S SESSION CONTENT FOR CONTEXT:
{session_content}

Use this content to inform your responses, but don't just recite it.
Deliver it naturally through conversation, adapted to their {learning_style} learning style.
"""
    return context

def get_scotty_response(user, user_message):
    """Get Scotty's AI response using Claude."""
    current_session = user['current_session'] or 1

    learning_style = user['learning_style'] or 'visual'
    session_content = ""
    try:
        lesson = run_async(course_reader.get_content(current_session, 'Lesson Content', learning_style=learning_style))
        ai_guidance = run_async(course_reader.get_content(current_session, 'AI Support Guidance', learning_style=learning_style))
        session_content = f"LESSON:\n{lesson}\n\nSCOTTY GUIDANCE:\n{ai_guidance}"
    except Exception as e:
        print(f"Error loading course content: {e}")

    history = get_conversation_history(user['id'], current_session, limit=8)

    context_prompt = build_context_prompt(user, session_content, history)
    system = SCOTTY_SYSTEM_PROMPT + "\n\n" + context_prompt

    messages = history + [{"role": "user", "content": user_message}]

    response = claude_client.messages.create(
        model="claude-opus-4-5",
        max_tokens=500,
        system=system,
        messages=messages
    )

    return response.content[0].text

# ── Auth Routes ────────────────────────────────────────

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    name = data.get('name', '').strip()

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    db = get_db()
    try:
        db.execute(
            'INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)',
            (email, generate_password_hash(password), name)
        )
        db.commit()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        session['user_id'] = user['id']
        return jsonify({'success': True, 'user': {'name': user['name'], 'email': user['email']}})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'already_exists'}), 409
    finally:
        db.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    db.close()

    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'error': 'Invalid email or password'}), 401

    session['user_id'] = user['id']
    learning_style = user['learning_style']
    onboarded = learning_style is not None and learning_style != '' and learning_style != 'null'
    return jsonify({
        'success': True,
        'user': {
            'name': user['name'],
            'email': user['email'],
            'current_session': user['current_session'],
            'learning_style': learning_style,
            'onboarded': onboarded
        }
    })

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/me')
def me():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401
    return jsonify({
        'id': user['id'],
        'name': user['name'],
        'email': user['email'],
        'current_session': user['current_session'],
        'learning_style': user['learning_style'],
        'pace': user['pace'],
        'avatar_enabled': bool(user['avatar_enabled'])
    })

# ── Onboarding ─────────────────────────────────────────

@app.route('/api/onboarding', methods=['POST'])
def save_onboarding():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json()
    learning_style = data.get('learning_style')
    pace = data.get('pace')
    outreach_push = data.get('outreach_push', True)
    outreach_sms = data.get('outreach_sms', False)
    outreach_whatsapp = data.get('outreach_whatsapp', False)
    outreach_phone = data.get('outreach_phone', '')

    db = get_db()
    db.execute('''
        UPDATE users SET
            learning_style = ?,
            pace = ?,
            outreach_push = ?,
            outreach_sms = ?,
            outreach_whatsapp = ?,
            outreach_phone = ?
        WHERE id = ?
    ''', (learning_style, pace, outreach_push, outreach_sms,
          outreach_whatsapp, outreach_phone, user['id']))
    db.commit()
    db.close()

    return jsonify({'success': True})

# ── Chat ───────────────────────────────────────────────

@app.route('/api/chat', methods=['POST'])
def chat():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json()
    message = data.get('message', '').strip()

    if not message:
        return jsonify({'error': 'Message required'}), 400

    current_session = user['current_session'] or 1

    try:
        save_message(user['id'], 'user', message, current_session)

        scotty_reply = get_scotty_response(user, message)

        save_message(user['id'], 'assistant', scotty_reply, current_session)

        db = get_db()
        db.execute('UPDATE users SET last_active = ? WHERE id = ?',
                   (datetime.now(timezone.utc), user['id']))
        db.commit()
        db.close()

        return jsonify({'response': scotty_reply, 'session': current_session})

    except Exception as e:
        print(f"Chat error: {e}")
        return jsonify({
            'response': "I'm here with you — just having a little moment. Try again in a sec? 💚",
            'error': str(e)
        }), 500

# ── Session / Course ───────────────────────────────────

@app.route('/api/session/<int:session_num>', methods=['GET'])
def get_session(session_num):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    if session_num < 1 or session_num > 10:
        return jsonify({'error': 'Invalid session number'}), 400

    try:
        style = user['learning_style'] or 'visual'
        content = run_async(course_reader.get_content(session_num, 'Lesson Content', learning_style=style))
        journal = run_async(course_reader.get_content(session_num, 'Journal Prompts', learning_style=style))
        exercise = run_async(course_reader.get_content(session_num, 'Daily Exercise', learning_style=style))
        motivation = run_async(course_reader.get_content(session_num, 'Motivation', learning_style=style))

        return jsonify({
            'session': session_num,
            'content': content,
            'journal_prompts': journal,
            'exercise': exercise,
            'motivation': motivation,
            'learning_style': style,
            'adapted': course_reader.adapted_exists(session_num, style)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/session/advance', methods=['POST'])
def advance_session():
    """Mark current session complete, move to next"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    current = user['current_session'] or 1
    next_session = min(current + 1, 10)

    db = get_db()
    db.execute('UPDATE users SET current_session = ? WHERE id = ?',
               (next_session, user['id']))
    db.commit()
    db.close()

    return jsonify({'success': True, 'new_session': next_session})

# ── Growth Notes ───────────────────────────────────────

@app.route('/api/notes', methods=['GET'])
def get_notes():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    db = get_db()
    notes = db.execute(
        'SELECT * FROM growth_notes WHERE user_id = ? ORDER BY created_at DESC',
        (user['id'],)
    ).fetchall()
    db.close()

    return jsonify({'notes': [dict(n) for n in notes]})

@app.route('/api/notes', methods=['POST'])
def save_note():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json()
    content = data.get('content', '').strip()
    sharing = data.get('sharing', 'private')
    wants_followup = data.get('wants_followup', False)

    if not content:
        return jsonify({'error': 'Note content required'}), 400

    db = get_db()
    db.execute(
        '''INSERT INTO growth_notes
           (user_id, content, sharing, session_num, wants_followup)
           VALUES (?, ?, ?, ?, ?)''',
        (user['id'], content, sharing, user['current_session'], wants_followup)
    )
    db.commit()
    db.close()

    return jsonify({'success': True})

# ── Mood Check-in ──────────────────────────────────────

@app.route('/api/mood', methods=['POST'])
def save_mood():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json()
    mood = data.get('mood', '')

    if not mood:
        return jsonify({'error': 'Mood required'}), 400

    db = get_db()
    db.execute(
        'INSERT INTO mood_checkins (user_id, mood, session_num) VALUES (?, ?, ?)',
        (user['id'], mood, user['current_session'])
    )
    db.commit()
    db.close()

    return jsonify({'success': True})

# ── Lesson Tea ─────────────────────────────────────────

@app.route('/api/tea/<int:session_num>', methods=['GET'])
def get_tea(session_num):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    db = get_db()
    posts = db.execute(
        '''SELECT lt.*, u.name as real_name
           FROM lesson_tea lt
           JOIN users u ON lt.user_id = u.id
           WHERE lt.session_num = ?
           ORDER BY lt.created_at DESC LIMIT 20''',
        (session_num,)
    ).fetchall()
    db.close()

    result = []
    for p in posts:
        post = dict(p)
        if post['anonymous']:
            post['display_name'] = post['display_name'] or 'Anonymous'
            del post['real_name']
        else:
            post['display_name'] = post['real_name']
        result.append(post)

    return jsonify({'posts': result, 'session': session_num})

@app.route('/api/tea', methods=['POST'])
def post_tea():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json()
    content = data.get('content', '').strip()
    anonymous = data.get('anonymous', True)
    display_name = data.get('display_name', None)

    if not content:
        return jsonify({'error': 'Content required'}), 400

    db = get_db()
    db.execute(
        '''INSERT INTO lesson_tea
           (user_id, session_num, content, anonymous, display_name)
           VALUES (?, ?, ?, ?, ?)''',
        (user['id'], user['current_session'], content, anonymous, display_name)
    )
    db.commit()
    db.close()

    return jsonify({'success': True})

# ── Stripe Webhook ─────────────────────────────────────

@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    """Handle Stripe purchase events"""
    payload = request.get_json()

    if not payload:
        return jsonify({'error': 'No payload'}), 400

    event_type = payload.get('type')

    if event_type == 'checkout.session.completed':
        stripe_session = payload.get('data', {}).get('object', {})
        email = stripe_session.get('customer_details', {}).get('email')
        name = stripe_session.get('customer_details', {}).get('name')
        customer_id = stripe_session.get('customer')

        if email:
            db = get_db()
            existing = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
            if not existing:
                db.execute(
                    'INSERT INTO users (email, password_hash, name, stripe_customer_id) VALUES (?, ?, ?, ?)',
                    (email, '', name, customer_id)
                )
                db.commit()
                print(f"✅ New user created from Stripe: {email}")
            db.close()

    return jsonify({'received': True})

# ── Avatar & Room ──────────────────────────────────────

@app.route('/api/room', methods=['POST'])
def save_room():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.get_json()
    room_config = json.dumps(data.get('room', {}))
    avatar_config = json.dumps(data.get('avatar', {}))

    db = get_db()
    db.execute(
        'UPDATE users SET room_config = ?, avatar_config = ? WHERE id = ?',
        (room_config, avatar_config, user['id'])
    )
    db.commit()
    db.close()

    return jsonify({'success': True})

@app.route('/api/room', methods=['GET'])
def get_room():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    return jsonify({
        'room': json.loads(user['room_config'] or '{}'),
        'avatar': json.loads(user['avatar_config'] or '{}'),
        'avatar_enabled': bool(user['avatar_enabled'])
    })

# ── Pages ──────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

# ── Run ────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    print(f"🤖 Scotty starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
