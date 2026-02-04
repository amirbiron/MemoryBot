"""
Memory Agent Bot - סוכן זיכרון אישי לפתרונות קוד
=================================================
בוט טלגרם עם MongoDB Atlas Vector Search ו-OpenAI Embeddings.
מאפשר לשמור פתרונות ולחפש אותם בשפה טבעית.

Author: Amir Chaim
Version: 1.0.0
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from pymongo import MongoClient, DESCENDING
from openai import OpenAI

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ==================== Configuration ====================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PUBLIC_URL = os.getenv("PUBLIC_URL")
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME", "memory_bot")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Validate required env vars
required_vars = {
    "BOT_TOKEN": BOT_TOKEN,
    "PUBLIC_URL": PUBLIC_URL,
    "MONGODB_URI": MONGODB_URI,
    "ADMIN_TELEGRAM_ID": ADMIN_TELEGRAM_ID,
    "OPENAI_API_KEY": OPENAI_API_KEY,
}
missing = [k for k, v in required_vars.items() if not v]
if missing:
    raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== OpenAI Embeddings ====================

openai_client = OpenAI(api_key=OPENAI_API_KEY)
EMBEDDING_MODEL = "text-embedding-3-small"
VECTOR_INDEX_NAME = "memories_vector_index"
EMBEDDING_DIMENSIONS = 1536  # text-embedding-3-small


def make_embedding(text: str) -> List[float]:
    """יצירת embedding לטקסט באמצעות OpenAI."""
    text = (text or "").strip()
    if not text:
        return []
    
    try:
        resp = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )
        return resp.data[0].embedding
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        return []


# ==================== MongoDB ====================

mongo = MongoClient(MONGODB_URI)
db = mongo[DB_NAME]
memories = db["memories"]

# יצירת אינדקסים בסיסיים
memories.create_index([("created_at", DESCENDING)])
memories.create_index([("tags", 1)])

# ==================== FSM States ====================

MODE_KEY = "mode"
DRAFT_KEY = "draft"
LAST_RESULTS_KEY = "last_results"

# States
MODE_NONE = "none"
MODE_SAVE_WAIT_TEXT = "save_wait_text"
MODE_SAVE_WAIT_TITLE = "save_wait_title"
MODE_SAVE_WAIT_TAGS = "save_wait_tags"
MODE_SAVE_CONFIRM = "save_confirm"
MODE_QUERY_WAIT_TEXT = "query_wait_text"
MODE_TAG_SEARCH_WAIT = "tag_search_wait"
MODE_DELETE_CONFIRM = "delete_confirm"

# ==================== UI Components ====================

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("➕ שמור פתרון"), KeyboardButton("🔎 שאל את הזיכרון")],
        [KeyboardButton("📚 רשימת זיכרונות"), KeyboardButton("🏷️ חיפוש לפי תגית")],
        [KeyboardButton("📊 סטטיסטיקות"), KeyboardButton("❓ עזרה")],
    ],
    resize_keyboard=True
)

CANCEL_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("❌ ביטול")]],
    resize_keyboard=True
)


def get_confirm_keyboard(memory_id: str = "") -> InlineKeyboardMarkup:
    """כפתורי אישור לשמירת זיכרון."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ שמור", callback_data=f"confirm_save:{memory_id}"),
            InlineKeyboardButton("❌ בטל", callback_data="cancel_save"),
        ],
        [
            InlineKeyboardButton("✏️ ערוך כותרת", callback_data="edit_title"),
            InlineKeyboardButton("✏️ ערוך תגיות", callback_data="edit_tags"),
        ]
    ])


def get_memory_actions_keyboard(memory_id: str) -> InlineKeyboardMarkup:
    """כפתורי פעולות על זיכרון."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 הצג מלא", callback_data=f"view_full:{memory_id}"),
            InlineKeyboardButton("🗑️ מחק", callback_data=f"delete:{memory_id}"),
        ]
    ])


# ==================== Helper Functions ====================

def is_admin(update: Update) -> bool:
    """בדיקה האם המשתמש הוא ה-admin."""
    user_id = update.effective_user.id if update.effective_user else 0
    return user_id == ADMIN_TELEGRAM_ID


def split_tags(s: str) -> List[str]:
    """פירוק מחרוזת תגיות לרשימה."""
    parts = [p.strip().lower() for p in s.replace("#", "").split(",")]
    return [p for p in parts if p]


def truncate_text(text: str, max_length: int = 200) -> str:
    """קיצור טקסט עם שלוש נקודות."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "…"


def format_memory_preview(doc: Dict[str, Any], index: int = 0) -> str:
    """פורמט תצוגה מקוצרת של זיכרון."""
    title = doc.get("title", "(ללא כותרת)")
    tags = doc.get("tags", [])
    solution = truncate_text(doc.get("solution", ""), 150)
    score = doc.get("score", 0)
    
    tags_str = ", ".join(tags) if tags else "(ללא תגיות)"
    score_str = f" (התאמה: {score:.0%})" if score else ""
    
    return f"**{index}) {title}**{score_str}\n🏷️ {tags_str}\n📝 {solution}\n"


def format_memory_full(doc: Dict[str, Any]) -> str:
    """פורמט תצוגה מלאה של זיכרון."""
    title = doc.get("title", "(ללא כותרת)")
    tags = doc.get("tags", [])
    solution = doc.get("solution", "")
    code = doc.get("code", "")
    created = doc.get("created_at")
    
    tags_str = ", ".join(tags) if tags else "(ללא תגיות)"
    date_str = created.strftime("%Y-%m-%d %H:%M") if created else ""
    
    text = f"📌 **{title}**\n\n"
    text += f"🏷️ תגיות: {tags_str}\n"
    text += f"📅 נוצר: {date_str}\n\n"
    text += f"📝 **פתרון:**\n{solution}\n"
    
    if code:
        text += f"\n💻 **קוד:**\n```\n{code}\n```"
    
    return text


def reset_user_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    """איפוס מצב המשתמש."""
    context.user_data[MODE_KEY] = MODE_NONE
    context.user_data.pop(DRAFT_KEY, None)
    context.user_data.pop(LAST_RESULTS_KEY, None)


# ==================== Database Operations ====================

def save_memory(doc: Dict[str, Any]) -> str:
    """שמירת זיכרון חדש עם embedding."""
    # יצירת embedding לחיפוש סמנטי
    to_embed = f"""
Title: {doc.get('title', '')}
Tags: {', '.join(doc.get('tags', []))}
Solution: {doc.get('solution', '')}
Context: {doc.get('context', '')}
    """.strip()
    
    doc["embedding"] = make_embedding(to_embed)
    doc["created_at"] = datetime.utcnow()
    doc["updated_at"] = datetime.utcnow()
    
    result = memories.insert_one(doc)
    return str(result.inserted_id)


def search_memories_vector(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """חיפוש סמנטי בזיכרונות עם Vector Search."""
    q_emb = make_embedding(query)
    
    if not q_emb:
        # Fallback לחיפוש טקסט פשוט
        return search_memories_text(query, limit)
    
    try:
        pipeline = [
            {
                "$vectorSearch": {
                    "index": VECTOR_INDEX_NAME,
                    "path": "embedding",
                    "queryVector": q_emb,
                    "numCandidates": 100,
                    "limit": limit
                }
            },
            {
                "$project": {
                    "title": 1,
                    "solution": 1,
                    "tags": 1,
                    "code": 1,
                    "created_at": 1,
                    "score": {"$meta": "vectorSearchScore"}
                }
            }
        ]
        
        results = list(memories.aggregate(pipeline))
        return results
        
    except Exception as e:
        logger.error(f"Vector search error: {e}")
        # Fallback לחיפוש טקסט
        return search_memories_text(query, limit)


def search_memories_text(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """חיפוש טקסט פשוט (fallback)."""
    # חיפוש במילים הראשונות של השאילתה
    search_term = query[:50]
    
    results = list(memories.find(
        {
            "$or": [
                {"title": {"$regex": search_term, "$options": "i"}},
                {"solution": {"$regex": search_term, "$options": "i"}},
                {"tags": {"$regex": search_term, "$options": "i"}},
            ]
        },
        {"title": 1, "solution": 1, "tags": 1, "code": 1, "created_at": 1}
    ).sort("created_at", -1).limit(limit))
    
    return results


def search_by_tag(tag: str, limit: int = 20) -> List[Dict[str, Any]]:
    """חיפוש לפי תגית."""
    return list(memories.find(
        {"tags": tag.lower()},
        {"title": 1, "tags": 1, "created_at": 1}
    ).sort("created_at", -1).limit(limit))


def get_recent_memories(limit: int = 10) -> List[Dict[str, Any]]:
    """קבלת זיכרונות אחרונים."""
    return list(memories.find(
        {},
        {"title": 1, "tags": 1, "created_at": 1}
    ).sort("created_at", -1).limit(limit))


def get_memory_by_id(memory_id: str) -> Optional[Dict[str, Any]]:
    """קבלת זיכרון לפי ID."""
    from bson import ObjectId
    try:
        return memories.find_one({"_id": ObjectId(memory_id)})
    except Exception:
        return None


def delete_memory(memory_id: str) -> bool:
    """מחיקת זיכרון."""
    from bson import ObjectId
    try:
        result = memories.delete_one({"_id": ObjectId(memory_id)})
        return result.deleted_count > 0
    except Exception:
        return False


def get_stats() -> Dict[str, Any]:
    """קבלת סטטיסטיקות."""
    total = memories.count_documents({})
    
    # תגיות פופולריות
    tag_pipeline = [
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5}
    ]
    top_tags = list(memories.aggregate(tag_pipeline))
    
    return {
        "total": total,
        "top_tags": top_tags
    }


# ==================== Handlers ====================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פקודת התחלה."""
    if not is_admin(update):
        await update.message.reply_text("🔒 סליחה, הבוט הזה פרטי.")
        return
    
    reset_user_state(context)
    
    await update.message.reply_text(
        "👋 היי! אני סוכן הזיכרון שלך.\n\n"
        "אני עוזר לך לשמור פתרונות ולמצוא אותם בקלות.\n"
        "בחר פעולה מהתפריט:",
        reply_markup=MAIN_KEYBOARD
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """פקודת עזרה."""
    if not is_admin(update):
        return
    
    await update.message.reply_text(
        "📚 **מה אני יכול לעשות:**\n\n"
        "➕ **שמור פתרון** - שמירת פתרון/קוד/טיפ חדש\n"
        "🔎 **שאל את הזיכרון** - חיפוש סמנטי בשפה טבעית\n"
        "📚 **רשימת זיכרונות** - הזיכרונות האחרונים\n"
        "🏷️ **חיפוש לפי תגית** - סינון לפי תגיות\n"
        "📊 **סטטיסטיקות** - נתונים על הזיכרונות\n\n"
        "💡 **טיפ:** כשאתה שומר, תן כותרת ברורה ותגיות רלוונטיות.",
        reply_markup=MAIN_KEYBOARD,
        parse_mode="Markdown"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler ראשי לכל ההודעות.
    מנתב לפי מצב השיחה הנוכחי.
    """
    if not is_admin(update):
        return
    
    text = (update.message.text or "").strip()
    mode = context.user_data.get(MODE_KEY, MODE_NONE)
    
    # ============ בדיקת כפתורי ביטול ============
    if text == "❌ ביטול":
        reset_user_state(context)
        await update.message.reply_text("❌ בוטל.", reply_markup=MAIN_KEYBOARD)
        return
    
    # ============ כפתורי תפריט ראשי ============
    if text == "➕ שמור פתרון":
        context.user_data[MODE_KEY] = MODE_SAVE_WAIT_TEXT
        context.user_data[DRAFT_KEY] = {}
        await update.message.reply_text(
            "📝 תדביק את הפתרון/הסבר/קוד שאתה רוצה לשמור.\n\n"
            "💡 טיפ: תכתוב הסבר ברור, אפשר גם להוסיף קוד.",
            reply_markup=CANCEL_KEYBOARD
        )
        return
    
    if text == "🔎 שאל את הזיכרון":
        context.user_data[MODE_KEY] = MODE_QUERY_WAIT_TEXT
        await update.message.reply_text(
            "🔎 מה אתה רוצה לחפש?\n\n"
            "דוגמאות:\n"
            "• איך פתרנו את בעיית ה-caching?\n"
            "• מה עשינו עם timeout ב-Render?\n"
            "• טיפול ב-race condition",
            reply_markup=CANCEL_KEYBOARD
        )
        return
    
    if text == "📚 רשימת זיכרונות":
        reset_user_state(context)
        docs = get_recent_memories(10)
        
        if not docs:
            await update.message.reply_text(
                "📭 אין עדיין זיכרונות שמורים.\n"
                "לחץ על ➕ שמור פתרון כדי להתחיל!",
                reply_markup=MAIN_KEYBOARD
            )
            return
        
        lines = ["📚 **הזיכרונות האחרונים:**\n"]
        for i, d in enumerate(docs, 1):
            dt = d.get("created_at")
            dt_str = dt.strftime("%d/%m/%y") if dt else ""
            title = d.get("title", "(ללא כותרת)")
            tags = ", ".join(d.get("tags", [])) or "-"
            lines.append(f"{i}. **{title}**\n   🏷️ {tags} | 📅 {dt_str}\n")
        
        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=MAIN_KEYBOARD,
            parse_mode="Markdown"
        )
        return
    
    if text == "🏷️ חיפוש לפי תגית":
        context.user_data[MODE_KEY] = MODE_TAG_SEARCH_WAIT
        
        # הצגת תגיות קיימות
        stats = get_stats()
        tags_info = ""
        if stats["top_tags"]:
            tags_list = [f"`{t['_id']}`" for t in stats["top_tags"]]
            tags_info = f"\n\n📊 תגיות פופולריות: {', '.join(tags_list)}"
        
        await update.message.reply_text(
            f"🏷️ כתוב תגית אחת לחיפוש:{tags_info}",
            reply_markup=CANCEL_KEYBOARD,
            parse_mode="Markdown"
        )
        return
    
    if text == "📊 סטטיסטיקות":
        reset_user_state(context)
        stats = get_stats()
        
        tags_text = ""
        if stats["top_tags"]:
            tags_lines = [f"  • {t['_id']}: {t['count']}" for t in stats["top_tags"]]
            tags_text = "\n\n🏷️ **תגיות פופולריות:**\n" + "\n".join(tags_lines)
        
        await update.message.reply_text(
            f"📊 **סטטיסטיקות:**\n\n"
            f"📝 סה\"כ זיכרונות: **{stats['total']}**"
            f"{tags_text}",
            reply_markup=MAIN_KEYBOARD,
            parse_mode="Markdown"
        )
        return
    
    if text == "❓ עזרה":
        await cmd_help(update, context)
        return
    
    # ============ FSM: שמירת פתרון ============
    if mode == MODE_SAVE_WAIT_TEXT:
        draft = context.user_data.get(DRAFT_KEY, {})
        draft["solution"] = text
        context.user_data[DRAFT_KEY] = draft
        context.user_data[MODE_KEY] = MODE_SAVE_WAIT_TITLE
        
        await update.message.reply_text(
            "✍️ מעולה! עכשיו תן כותרת קצרה לזיכרון.\n\n"
            "דוגמה: \"פתרון N+1 queries עם Redis cache\"",
            reply_markup=CANCEL_KEYBOARD
        )
        return
    
    if mode == MODE_SAVE_WAIT_TITLE:
        draft = context.user_data.get(DRAFT_KEY, {})
        draft["title"] = text
        context.user_data[DRAFT_KEY] = draft
        context.user_data[MODE_KEY] = MODE_SAVE_WAIT_TAGS
        
        await update.message.reply_text(
            "🏷️ תגיות? כתוב עם פסיקים.\n\n"
            "דוגמה: `mongo, redis, cache, performance`\n\n"
            "אם אין תגיות, כתוב `-`",
            reply_markup=CANCEL_KEYBOARD,
            parse_mode="Markdown"
        )
        return
    
    if mode == MODE_SAVE_WAIT_TAGS:
        draft = context.user_data.get(DRAFT_KEY, {})
        tags = [] if text == "-" else split_tags(text)
        draft["tags"] = tags
        context.user_data[DRAFT_KEY] = draft
        context.user_data[MODE_KEY] = MODE_SAVE_CONFIRM
        
        # הצגת תצוגה מקדימה לאישור
        preview = (
            "📋 **תצוגה מקדימה:**\n\n"
            f"📌 **כותרת:** {draft['title']}\n"
            f"🏷️ **תגיות:** {', '.join(tags) if tags else '(ללא)'}\n\n"
            f"📝 **תוכן:**\n{truncate_text(draft['solution'], 300)}\n\n"
            "האם לשמור?"
        )
        
        await update.message.reply_text(
            preview,
            reply_markup=get_confirm_keyboard(),
            parse_mode="Markdown"
        )
        return
    
    # ============ FSM: שאילתת זיכרון ============
    if mode == MODE_QUERY_WAIT_TEXT:
        reset_user_state(context)
        
        await update.message.reply_text("🔍 מחפש...")
        
        results = search_memories_vector(text, limit=5)
        
        if not results:
            await update.message.reply_text(
                "😕 לא מצאתי זיכרונות רלוונטיים.\n\n"
                "💡 טיפ: נסה לנסח אחרת או להשתמש במילות מפתח אחרות.",
                reply_markup=MAIN_KEYBOARD
            )
            return
        
        # שמירת תוצאות לפעולות המשך
        context.user_data[LAST_RESULTS_KEY] = results
        
        lines = [f"🧠 **מצאתי {len(results)} זיכרונות רלוונטיים:**\n"]
        for i, doc in enumerate(results, 1):
            lines.append(format_memory_preview(doc, i))
        
        # יצירת כפתורים לתוצאות
        buttons = []
        for i, doc in enumerate(results, 1):
            memory_id = str(doc["_id"])
            buttons.append([
                InlineKeyboardButton(f"📖 הצג {i}", callback_data=f"view_full:{memory_id}"),
                InlineKeyboardButton(f"🗑️ מחק {i}", callback_data=f"delete:{memory_id}")
            ])
        
        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else MAIN_KEYBOARD,
            parse_mode="Markdown"
        )
        return
    
    # ============ FSM: חיפוש תגית ============
    if mode == MODE_TAG_SEARCH_WAIT:
        reset_user_state(context)
        tag = text.strip().lower().replace("#", "")
        
        docs = search_by_tag(tag, limit=20)
        
        if not docs:
            await update.message.reply_text(
                f"😕 לא מצאתי זיכרונות עם התגית `{tag}`.",
                reply_markup=MAIN_KEYBOARD,
                parse_mode="Markdown"
            )
            return
        
        lines = [f"🏷️ **זיכרונות עם תגית `{tag}`:**\n"]
        for i, d in enumerate(docs, 1):
            dt = d.get("created_at")
            dt_str = dt.strftime("%d/%m/%y") if dt else ""
            lines.append(f"{i}. {d.get('title', '(ללא כותרת)')} | 📅 {dt_str}")
        
        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=MAIN_KEYBOARD,
            parse_mode="Markdown"
        )
        return
    
    # ============ ברירת מחדל ============
    await update.message.reply_text(
        "🙂 בחר פעולה מהתפריט למטה.",
        reply_markup=MAIN_KEYBOARD
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """טיפול בכפתורי inline."""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(update):
        return
    
    data = query.data
    
    # ============ אישור שמירה ============
    if data.startswith("confirm_save"):
        draft = context.user_data.get(DRAFT_KEY, {})
        
        if not draft:
            await query.edit_message_text("❌ אין טיוטה לשמירה.", reply_markup=None)
            return
        
        doc = {
            "title": draft.get("title", "(ללא כותרת)"),
            "solution": draft.get("solution", ""),
            "tags": draft.get("tags", []),
            "context": "",
            "code": "",
        }
        
        memory_id = save_memory(doc)
        reset_user_state(context)
        
        await query.edit_message_text(
            f"✅ **נשמר בהצלחה!**\n\n"
            f"📌 {doc['title']}\n"
            f"🏷️ {', '.join(doc['tags']) if doc['tags'] else '(ללא תגיות)'}\n\n"
            f"🔑 ID: `{memory_id}`",
            parse_mode="Markdown"
        )
        return
    
    # ============ ביטול שמירה ============
    if data == "cancel_save":
        reset_user_state(context)
        await query.edit_message_text("❌ השמירה בוטלה.")
        return
    
    # ============ עריכת כותרת ============
    if data == "edit_title":
        context.user_data[MODE_KEY] = MODE_SAVE_WAIT_TITLE
        await query.edit_message_text(
            "✍️ כתוב כותרת חדשה:",
            reply_markup=None
        )
        return
    
    # ============ עריכת תגיות ============
    if data == "edit_tags":
        context.user_data[MODE_KEY] = MODE_SAVE_WAIT_TAGS
        await query.edit_message_text(
            "🏷️ כתוב תגיות חדשות (עם פסיקים):",
            reply_markup=None
        )
        return
    
    # ============ הצגת זיכרון מלא ============
    if data.startswith("view_full:"):
        memory_id = data.split(":")[1]
        doc = get_memory_by_id(memory_id)
        
        if not doc:
            await query.edit_message_text("❌ הזיכרון לא נמצא.")
            return
        
        await query.message.reply_text(
            format_memory_full(doc),
            reply_markup=get_memory_actions_keyboard(memory_id),
            parse_mode="Markdown"
        )
        return
    
    # ============ מחיקת זיכרון ============
    if data.startswith("delete:"):
        memory_id = data.split(":")[1]
        doc = get_memory_by_id(memory_id)
        
        if not doc:
            await query.edit_message_text("❌ הזיכרון לא נמצא.")
            return
        
        context.user_data[DRAFT_KEY] = {"delete_id": memory_id}
        context.user_data[MODE_KEY] = MODE_DELETE_CONFIRM
        
        await query.message.reply_text(
            f"⚠️ **למחוק את הזיכרון?**\n\n"
            f"📌 {doc.get('title', '(ללא כותרת)')}\n\n"
            f"זה לא ניתן לביטול!",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🗑️ כן, מחק", callback_data=f"confirm_delete:{memory_id}"),
                    InlineKeyboardButton("❌ לא", callback_data="cancel_delete"),
                ]
            ]),
            parse_mode="Markdown"
        )
        return
    
    # ============ אישור מחיקה ============
    if data.startswith("confirm_delete:"):
        memory_id = data.split(":")[1]
        
        if delete_memory(memory_id):
            await query.edit_message_text("✅ הזיכרון נמחק.")
        else:
            await query.edit_message_text("❌ שגיאה במחיקה.")
        
        reset_user_state(context)
        return
    
    # ============ ביטול מחיקה ============
    if data == "cancel_delete":
        reset_user_state(context)
        await query.edit_message_text("❌ המחיקה בוטלה.")
        return


# ==================== FastAPI Application ====================

app = FastAPI(title="Memory Agent Bot")
ptb_app = Application.builder().token(BOT_TOKEN).build()

# Register handlers
ptb_app.add_handler(CommandHandler("start", cmd_start))
ptb_app.add_handler(CommandHandler("help", cmd_help))
ptb_app.add_handler(CallbackQueryHandler(handle_callback))
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


@app.on_event("startup")
async def on_startup():
    """הפעלת webhook בעת עלייה."""
    webhook_url = f"{PUBLIC_URL}/webhook/{WEBHOOK_SECRET}"
    await ptb_app.bot.set_webhook(url=webhook_url)
    await ptb_app.initialize()
    await ptb_app.start()
    logger.info(f"Webhook set to: {webhook_url}")


@app.on_event("shutdown")
async def on_shutdown():
    """סגירה נקייה."""
    await ptb_app.stop()
    await ptb_app.shutdown()


@app.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    """קבלת עדכונים מטלגרם."""
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)
    return {"ok": True}


@app.get("/")
def health():
    """בדיקת תקינות."""
    return {"status": "ok", "bot": "Memory Agent"}


@app.get("/stats")
def api_stats():
    """API לסטטיסטיקות."""
    return get_stats()
