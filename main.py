import telebot
from telebot import types
import sqlite3
import time

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = '8520204152:AAFbHZNlXXmVGfd1SLE8P_ehEmH-Tvb9--0'
ADMIN_USERNAME = 'roxydiamond'
MAIN_CHANNEL_ID = '@crmp_slay' # Сюда бот проверяет подписку через API
ADMIN_CHAT_ID = None 

bot = telebot.TeleBot(BOT_TOKEN)

# --- РАБОТА С БАЗОЙ ДАННЫХ ---
def db_query(query, params=(), fetch=False):
    """Безопасное выполнение запросов к БД"""
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(query, params)
    data = cursor.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return data

def init_db():
    # Пользователи
    db_query('''CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance REAL DEFAULT 0,
                referrer_id INTEGER,
                refs_count INTEGER DEFAULT 0,
                is_vip INTEGER DEFAULT 0,
                last_bonus_time REAL DEFAULT 0
            )''')
    # Ссылки для ОП
    db_query('''CREATE TABLE IF NOT EXISTS socials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT,
                link TEXT,
                btn_text TEXT
            )''')
    # Проверка основного ТГ канала
    res = db_query("SELECT count(*) FROM socials WHERE platform='telegram'", fetch=True)
    if res[0][0] == 0:
        db_query("INSERT INTO socials (platform, link, btn_text) VALUES (?, ?, ?)", 
                 ('telegram', f"https://t.me/{MAIN_CHANNEL_ID.replace('@', '')}", "📢 Наш канал (ОБЯЗАТЕЛЬНО)"))

init_db()

# --- ПРОВЕРКИ ---
def check_sub(user_id):
    """Проверка подписки на основной канал"""
    try:
        status = bot.get_chat_member(MAIN_CHANNEL_ID, user_id).status
        return status in ['creator', 'administrator', 'member']
    except:
        return False

# --- КЛАВИАТУРЫ ---
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("👤 Профиль", "💰 Заработать")
    markup.add("📤 Вывод", "📊 Статистика")
    markup.add("🎁 Бонус", "👑 VIP")
    markup.add("🆘 Техподдержка")
    return markup

def get_admin_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("➕ Дать ₽", "➖ Снять ₽")
    markup.add("📈 Статистика бота", "👑 Дать VIP")
    markup.add("🔗 Добавить ОП", "🗑 Удалить ОП")
    markup.add("📢 Рассылка", "🔙 Меню юзера")
    return markup

def get_sub_inline():
    markup = types.InlineKeyboardMarkup(row_width=1)
    links = db_query("SELECT link, btn_text FROM socials", fetch=True)
    for link, text in links:
        markup.add(types.InlineKeyboardButton(text, url=link))
    markup.add(types.InlineKeyboardButton("✅ Я подписался!", callback_data="check_subscription"))
    return markup

# --- ОБРАБОТЧИК /START ---
@bot.message_handler(commands=['start', 'admin'])
def start_cmd(message):
    global ADMIN_CHAT_ID
    uid = message.from_user.id
    uname = message.from_user.username if message.from_user.username else "User"
    
    # Регистрация админа
    if uname.lower() == ADMIN_USERNAME.lower():
        ADMIN_CHAT_ID = uid
        if message.text == '/admin':
            return bot.send_message(uid, "🛠 Админ-панель активна:", reply_markup=get_admin_menu())

    # Регистрация пользователя и рефералка
    user_exists = db_query("SELECT user_id FROM users WHERE user_id=?", (uid,), fetch=True)
    if not user_exists:
        ref_id = None
        if len(message.text.split()) > 1:
            try:
                ref_id = int(message.text.split()[1])
                if ref_id == uid: ref_id = None
            except: ref_id = None
        
        db_query("INSERT INTO users (user_id, username, referrer_id) VALUES (?, ?, ?)", (uid, uname, ref_id))
        
        if ref_id:
            ref_data = db_query("SELECT is_vip FROM users WHERE user_id=?", (ref_id,), fetch=True)
            if ref_data:
                reward = 20 if ref_data[0][0] == 1 else 10
                db_query("UPDATE users SET balance = balance + ?, refs_count = refs_count + 1 WHERE user_id=?", (reward, ref_id))
                try: bot.send_message(ref_id, f"💎 У вас новый реферал @{uname}! Начислено {reward}₽")
                except: pass

    # Проверка подписки
    if not check_sub(uid):
        return bot.send_message(uid, "⚠️ Чтобы использовать бота, подпишитесь на наши соцсети:", reply_markup=get_sub_inline())

    bot.send_message(uid, f"👋 Привет, {message.from_user.first_name}!", reply_markup=get_main_menu())

# --- CALLBACKS ---
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    uid = call.from_user.id
    if call.data == "check_subscription":
        if check_sub(uid):
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(uid, "🎉 Спасибо за подписку! Теперь функции доступны.", reply_markup=get_main_menu())
        else:
            bot.answer_callback_query(call.id, "❌ Подписка на канал @crmp_slay не найдена!", show_alert=True)
    
    elif call.data.startswith("del_op_"):
        op_id = call.data.split("_")[2]
        db_query("DELETE FROM socials WHERE id=?", (op_id,))
        bot.answer_callback_query(call.id, "Удалено!")
        bot.edit_message_text("✅ Ссылка успешно удалена из ОП.", call.message.chat.id, call.message.message_id)

# --- ГЛАВНЫЙ ОБРАБОТЧИК ---
@bot.message_handler(content_types=['text', 'photo', 'video'])
def main_logic(message):
    uid = message.from_user.id
    text = message.text
    uname = message.from_user.username
    
    user = db_query("SELECT * FROM users WHERE user_id=?", (uid,), fetch=True)
    if not user: return

    # Данные юзера из БД
    u_id, u_name, u_bal, u_ref_id, u_refs, u_vip, u_bonus = user[0]

    # --- АДМИН ПАНЕЛЬ ---
    if uname and uname.lower() == ADMIN_USERNAME.lower():
        if text == "📢 Рассылка":
            msg = bot.send_message(uid, "Отправьте текст, фото или видео для рассылки всем юзерам:")
            bot.register_next_step_handler(msg, run_broadcast)
            return
        elif text == "➕ Дать ₽":
            msg = bot.send_message(uid, "Введите: `юзернейм сумма` (без @)")
            bot.register_next_step_handler(msg, admin_money_op, True)
            return
        elif text == "➖ Снять ₽":
            msg = bot.send_message(uid, "Введите: `юзернейм сумма` (без @)")
            bot.register_next_step_handler(msg, admin_money_op, False)
            return
        elif text == "👑 Дать VIP":
            msg = bot.send_message(uid, "Введите юзернейм для выдачи VIP:")
            bot.register_next_step_handler(msg, admin_give_vip)
            return
        elif text == "📈 Статистика бота":
            total = db_query("SELECT COUNT(*) FROM users", fetch=True)[0][0]
            return bot.send_message(uid, f"📊 Всего пользователей в базе: {total}")
        elif text == "🔗 Добавить ОП":
            msg = bot.send_message(uid, "Формат: `Тип Ссылка Текст_Кнопки` (через пробел, текст без пробелов)")
            bot.register_next_step_handler(msg, admin_add_op)
            return
        elif text == "🗑 Удалить ОП":
            ops = db_query("SELECT id, platform, btn_text FROM socials WHERE platform != 'telegram'", fetch=True)
            if not ops: return bot.send_message(uid, "Дополнительных ссылок нет.")
            m = types.InlineKeyboardMarkup()
            for sid, plat, btxt in ops:
                m.add(types.InlineKeyboardButton(f"❌ {btxt} ({plat})", callback_data=f"del_op_{sid}"))
            return bot.send_message(uid, "Выберите ссылку для удаления:", reply_markup=m)
        elif text == "🔙 Меню юзера":
            return bot.send_message(uid, "Переключено в режим пользователя.", reply_markup=get_main_menu())

    # --- МЕНЮ ПОЛЬЗОВАТЕЛЯ ---
    if text == "👤 Профиль":
        st = "💎 VIP" if u_vip else "Обычный"
        msg = f"👤 **Ваш профиль:**\n\n🆔 ID: `{uid}`\n👤 Логин: @{u_name}\n💰 Баланс: {u_bal}₽\n👥 Друзей: {u_refs}\n👑 Статус: {st}"
        bot.send_message(uid, msg, parse_mode='Markdown')

    elif text == "💰 Заработать":
        link = f"https://t.me/{bot.get_me().username}?start={uid}"
        rew = 20 if u_vip else 10
        bot.send_message(uid, f"💸 Платим за каждого друга!\n🎁 Ваша награда: **{rew}₽**\n\n🔗 Ссылка:\n`{link}`", parse_mode='Markdown')

    elif text == "🎁 Бонус":
        if time.time() - u_bonus > 86400:
            db_query("UPDATE users SET balance = balance + 10, last_bonus_time = ? WHERE user_id=?", (time.time(), uid))
            bot.send_message(uid, "🎁 Вы получили ежедневный бонус 10₽!")
        else:
            h = int((86400 - (time.time() - u_bonus)) // 3600)
            bot.send_message(uid, f"⏳ Бонус будет доступен через {h} ч.")

    elif text == "📊 Статистика":
        top = db_query("SELECT username, refs_count FROM users ORDER BY refs_count DESC LIMIT 5", fetch=True)
        msg = "🏆 **ТОП-5 Рефоводов:**\n\n"
        for i, (name, count) in enumerate(top, 1):
            msg += f"{i}. @{name} — {count} приглашенных\n"
        bot.send_message(uid, msg, parse_mode='Markdown')

    elif text == "📤 Вывод":
        if u_bal < 300: return bot.send_message(uid, f"❌ Минимальная сумма — 300₽. Ваш баланс: {u_bal}₽")
        m = types.ReplyKeyboardMarkup(resize_keyboard=True); m.add("CryptoBot", "Dushanbe City")
        msg = bot.send_message(uid, "Выберите платежную систему:", reply_markup=m)
        bot.register_next_step_handler(msg, withdraw_req)

    elif text == "👑 VIP":
        bot.send_message(uid, "💎 **VIP ПРЕИМУЩЕСТВА**\n\n• Доход за друга: 20₽ (вместо 10₽)\n• Моментальный вывод\n\n💳 Цена: 150₽\nДля покупки: @roxydiamond")

    elif text == "🆘 Техподдержка":
        msg = bot.send_message(uid, "Опишите вашу проблему в одном сообщении:")
        bot.register_next_step_handler(msg, lambda m: bot.send_message(ADMIN_CHAT_ID, f"🆘 **Жалоба от @{m.from_user.username}:**\n{m.text}") if ADMIN_CHAT_ID else None)

# --- АДМИН ФУНКЦИИ ---
def run_broadcast(message):
    users = db_query("SELECT user_id FROM users", fetch=True)
    bot.send_message(message.chat.id, f"🚀 Начинаю рассылку для {len(users)} пользователей...")
    c = 0
    for u in users:
        try:
            if message.content_type == 'text': bot.send_message(u[0], message.text)
            elif message.content_type == 'photo': bot.send_photo(u[0], message.photo[-1].file_id, caption=message.caption)
            elif message.content_type == 'video': bot.send_video(u[0], message.video.file_id, caption=message.caption)
            c += 1; time.sleep(0.05)
        except: pass
    bot.send_message(message.chat.id, f"✅ Рассылка завершена! Доставлено: {c}")

def admin_money_op(message, add):
    try:
        user, amount = message.text.split(); op = "+" if add else "-"
        db_query(f"UPDATE users SET balance = balance {op} ? WHERE username = ?", (float(amount), user.replace('@','')))
        bot.send_message(message.chat.id, "✅ Баланс успешно изменен.")
    except: bot.send_message(message.chat.id, "Ошибка! Формат: `roxydiamond 100`")

def admin_give_vip(message):
    db_query("UPDATE users SET is_vip = 1 WHERE username = ?", (message.text.replace('@',''),))
    bot.send_message(message.chat.id, "✅ VIP выдан.")

def admin_add_op(message):
    try:
        parts = message.text.split(None, 2)
        db_query("INSERT INTO socials (platform, link, btn_text) VALUES (?, ?, ?)", (parts[0], parts[1], parts[2]))
        bot.send_message(message.chat.id, "✅ Ссылка добавлена в обязательную подписку.")
    except: bot.send_message(message.chat.id, "Ошибка! Пример: `TikTok https://.. Подпишись_в_ТТ` (без пробелов в тексте)")

# --- ВЫВОД ---
def withdraw_req(message):
    method = message.text
    msg = bot.send_message(message.chat.id, f"Введите реквизиты для вывода на {method}:")
    bot.register_next_step_handler(msg, withdraw_done, method)

def withdraw_done(message, method):
    uid = message.from_user.id
    balance = db_query("SELECT balance FROM users WHERE user_id=?", (uid,), fetch=True)[0][0]
    db_query("UPDATE users SET balance = 0 WHERE user_id=?", (uid,))
    bot.send_message(uid, "✅ Заявка отправлена! Ожидайте выплаты от администратора.", reply_markup=get_main_menu())
    if ADMIN_CHAT_ID:
        bot.send_message(ADMIN_CHAT_ID, f"💰 **ЗАЯВКА НА ВЫВОД**\n\n👤 Юзер: @{message.from_user.username}\n💎 Сумма: {balance}₽\n💳 Метод: {method}\n📝 Реквизиты: `{message.text}`", parse_mode='Markdown')

# --- ЗАПУСК ---
if __name__ == "__main__":
    print("Бот успешно запущен!")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
