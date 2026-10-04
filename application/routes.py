from application import data as config
import telebot
import time
import flask
import hmac
from application import payments_api
from flask import Blueprint, request
from .models import db, User, Group, Member
import datetime
import collections
import logging
import coinbase_commerce as cc
from coinbase_commerce.error import WebhookInvalidPayload, SignatureVerificationError
from coinbase_commerce.webhook import Webhook
logger = telebot.logger
telebot.logger.setLevel(logging.ERROR)

client = cc.Client(config.coinbase_api_key)

logging.basicConfig(
    filename='flow.log', 
    encoding='utf-8', 
    level=logging.DEBUG)
logger=logging.getLogger(__name__)
bot = telebot.TeleBot(config.token, threaded=False)
blueprint = Blueprint("routes", __name__)

@blueprint.route(config.telegram_webhook_path, methods=['POST'])
def webhook():
    if flask.request.headers.get('content-type', '').startswith('application/json'):
        if not hmac.compare_digest(
            flask.request.headers.get('X-Telegram-Bot-Api-Secret-Token', ''),
            config.telegram_webhook_secret,
        ):
            flask.abort(403)
        json_string = flask.request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "ok", 200
    else:
        flask.abort(403)

@blueprint.route(config.coinbase_webhook_path, methods=['POST'])
def redirecthandler():
    request_data = request.data.decode('utf-8')
    # webhook signature
    request_sig = request.headers.get('X-CC-Webhook-Signature', None)

    try:
        # signature verification and event object construction
        event = Webhook.construct_event(request_data, request_sig, config.cc_secret_header)
    except (WebhookInvalidPayload, SignatureVerificationError) as e:
        return str(e), 400
    if event.type =="charge:confirmed":
        charge = client.charge.retrieve(event.data.code)
        amt = 0.00
        for payment in charge.payments:
            amt += float(payment.net.local.amount)
        if 1<len(charge.payments):
            bot.send_message(config.dummychatid, "Rectify: {(charge.payments, charge.description, amt)}")
        
        chat_id = str(charge.description).split("-")[1]
        credit((chat_id, amt))
        return "ok", 200
    return "ok", 200

def broadcast(chat_list, text):
    for chatid in chat_list:
        try:
            bot.send_message(chatid, text)
        except:
            continue

def register(chat_id):
    chat_id = str(chat_id)
    q=db.session.query(User).filter_by(
    chat_id=str(chat_id)).first()
    print(q)
    if q:
        print("also")
        return True
    else:
        print("g")
        u = User(chat_id=str(chat_id), wallet=0.00)
        
        db.session.add(u)
        db.session.commit()
        print("also")
        return False

def credit(data):
    user = db.session.query(User).filter_by(chat_id=str(data[0])).first()
    if not user:
        print("Serious error, user not found in payment")
        return
    user.wallet += data[1]
    db.session.commit()
    bot.send_message(data[0], f"Deposit Credited: ${data[1]}")

def profit(gainz):
    with open("gains.txt", "a") as f:
        f.write(f"\n+{gainz}")

def settle_payment(from_user, to, chat):
    from_user.wallet -= chat.cost
    act_price = config.percent*chat.cost
    to.wallet += act_price
    chat.profit += act_price
    profit(chat.cost-act_price)
    db.session.commit()
    return 200

def support(msg):
    t = msg.text
    bot.send_message(config.dummychatid, t)
    bot.send_message(msg.chat.id, "Message Sent!")

def get_subscriptions(chatid):
    s = db.session.query(Member).filter_by(
    chat_id=str(chatid)).all()
    return s

def is_user_subscribed(userid, chatid):
    try:
        db.session.query(Member).filter_by(chat_id=str(userid), group_chat_id=str(chatid)).one()
        return True
    except:
        return False

def is_user_member(userid, chatid):
    return bot.get_chat_member(chatid, userid)

def subscribe_user(userid, chatid):
    user = db.session.query(User).filter_by(
    chat_id=str(userid)).first()
    chat = db.session.query(Group).filter_by(
    chat_id=str(chatid)).first()
    chat_admin=chat.user
    bot.unban_chat_member(chatid, int(userid))
    if user is None or chat is None:
        return 3
    bal = user.wallet
    if bal < chat.cost:
        return 2
    else:
        t = settle_payment(user, chat_admin, chat)
        if t == 200:
            return 1
        else:
            return 3

def unsubscribe_user(userid, chatid):
    user = db.session.query(User).filter_by(
    chat_id=str(userid)).first()
    chat = db.session.query(Group).filter_by(
    chat_id=str(chatid)).first()
    if user is None or chat is None:
        return False
    m = db.session.query(Member).filter_by(
    chat_id=str(userid), group_chat_id=str(chatid)).first()
    db.session.delete(m)
    db.session.commit()
    try:
        bot.ban_chat_member(chatid, userid)
    except:
        print('Failed to ban')
    return True
def new2(msg):
    if "Cancel" in msg.text:
        bot.send_message(msg.chat.id,
        config.starttext,
        reply_markup=config.startmarkup)
        return
    else:
        bot.send_message(msg.chat.id, """
How much does each Subscriber pay per month? (In USD with no symbols. eg, 15.5)""")
        bot.register_next_step_handler(msg, new3)


def removechat(userid, chatid):
    chatid = str(chatid)
    userid = str(userid)
    chat = db.session.query(Group).filter_by(
    chat_id=str(chatid)).first()
    chat_admin = db.session.query(User).filter_by(
    chat_id=chat.user.chat_id).first()
    if str(chat_admin.chat_id) == str(userid):
        db.session.delete(chat)
        f = db.session.query(Member.chat_id).filter_by(
        group_chat_id=str(chatid)).all()
        f = [x[0] for x in f]
        db.session.query(Member).filter_by(
        group_chat_id=str(chatid)).delete()
        db.session.commit()
        l = bot.get_chat(chatid)
        broadcast(f, f"A chat you were a member of, {l.title} was removed by the admin, and no longer uses this bot. You will no longer be charged for membership via this bot.")
    else:
        bot.send_message(userid, 'Insufficient permissions for this action')
def new3(msg):
    if "Cancel" in msg.text:
        bot.send_message(msg.chat.id,
        config.starttext,
        reply_markup=config.startmarkup)
        return
    try:
        x = abs(float(msg.text))
    except:
        bot.send_message(msg.chat.id, 
        "Invalid input", 
        reply_markup=config.startmarkup)
        return
    price = str((((1-config.percent)+1)*x))
    price = float(price.split("."
    )[0] +"."+price.split(".")[1][0:2])
    bot.send_message(msg.chat.id, """
Create a new private channel/group

<b>For Channels</b>
Next, forward any message from the channel to the bot. 
Make sure all the earlier privileges are correct before completing this step.

<b>For Groups</b>
If its a Private Group, Send /start inside the group and forward the bot's response back here""", parse_mode="html")
    bot.register_next_step_handler(msg, new4, price)
    return

def new4(msg, price):
    if "Cancel" in msg.text:
        bot.send_message(msg.chat.id,
        config.starttext,
        reply_markup=config.startmarkup)
        return
    try:
        if "Your Chat Id:" in msg.text:
            chatid = msg.text.replace(
            "Your Chat Id: ","")
        else:
            chatid = msg.forward_from_chat.id
            check = db.session.query(Group).filter_by(
            chat_id=str(chatid)).first()
            if check is not None:
                bot.send_message(msg.chat.id, "This chat has already been registered")
                return
            g = Group(chat_id=str(chatid), cost=abs(price), 
                admin_id = msg.chat.id, profit=0.00)
            target_group = int(g.chat_id)
            db.session.add(g)
            db.session.commit()
            reflink = f"t.me/{config.botusername}?start=g{chatid}"
            
            bot.send_message(msg.chat.id,  f"""
This is your group link:

{reflink}

Send it to anyone to allow them to join on premium. With this link, users pay before they are given access to the channel.

If you have users that are already subscribed, Forward a message from the old channel (not the one you just created).

Private Group:
Send start in the chat(in the old group, not the one you just created) and forward the bots message here if its a private group

We'll generate a link that will allow your old subscribers to join for one month without paying again. Click cancel to access the main menu
""")
            bot.register_next_step_handler(msg, new5, price, target_group)
    except AttributeError as e:
        print(e)
        bot.send_message(msg.chat.id, "If its a Private Group, Send /start inside the group and forward the message to the bot")
        bot.register_next_step_handler(msg, new4, price)
    except Exception as e:
            print(e)
            bot.send_message(msg.chat.id, "An error occured! please make sure the relevant permissions were given!", reply_markup=config.startmarkup)

def new5(msg, price, target_group):
    if "Cancel" in msg.text:
        bot.send_message(msg.chat.id,
        config.starttext,
        reply_markup=config.startmarkup)
        return
    if "Your Chat Id:" in msg.text:
        old_group = msg.text.replace(
        "Your Chat Id: ","")
    else:
        old_group = msg.forward_from_chat.id
    if old_group == target_group:
        bot.send_message(msg.chat.id, "This is from the new chat you created. Forward a message from your old premium chat")
        bot.register_next_step_handler(msg, new5, price, target_group)
        return
    elif bot.get_chat(old_group).type == "private":
        bot.send_message(msg.chat.id, "Cancelled.", reply_markup=config.startmarkup)
        return
    exp = datetime.date.today()+datetime.timedelta(days=30)
    exp2 = time.mktime(exp.timetuple())
    reflink = f"t.me/{config.botusername}?start={old_group}/{target_group}/{exp2}"
    bot.send_message(msg.chat.id,
    f"""
This link will be valid for 1 month:

{reflink}

It will allow any user who is a member of your old channel to join the new one for free for one month""", reply_markup=config.startmarkup)
def withdraw1(msg):
    if "Cancel" in msg.text:
        bot.send_message(msg.chat.id, "Cancelled!", reply_markup=config.startmarkup)
        return
    bot.send_message(msg.chat.id, "Send the amount you want to withdraw (in USD)", reply_markup=config.cancel)
    bot.register_next_step_handler(msg, withdraw2, msg.text)
    return

def withdraw2(msg, address):
    if "Cancel" in msg.text:
        bot.send_message(msg.chat.id, "Cancelled!", reply_markup=config.startmarkup)
        return
    try:
        amt = float(msg.text)
        bal = db.session.query(User.wallet).filter_by(chat_id=str(msg.chat.id)).first()[0]
        if amt < config.withmin:
            bot.send_message(msg.chat.id, "Requested amount is lower than 10 USD (Minimum withdrawal)", reply_markup=config.startmarkup)
            return
        if amt < bal:
            bot.send_message(msg.chat.id, f"Insufficient funds to complete this operation. You have ${bal}", reply_markup=config.startmarkup)
            return
        bal -= amt
        withdrawfinal(msg.chat.id, amt, address)
        bot.send_message(msg.chat.id,
    "Your withdrawal request is being processed, and may take a few hours. Payment requests are authorized manually to prevent theft. Have a nice day!", reply_markup=config.startmarkup)
        db.session.commit()
    except:
        bot.send_message(msg.chat.id, "Invalid Input", reply_markup=config.startmarkup)

def withdrawfinal(uid, amt, address):
    bal = db.session.query(User.wallet).filter_by(chat_id=str(uid)).first()[0]
    bot.send_message(config.dummychatid, 
    f"""
    Payout Withdrawal to {uid}
    Balance(new): {bal}
    Address: {address}
    Amount(USDT): {amt}
    """, reply_markup=config.wfinalmarkup(uid, amt)
    )
@bot.message_handler(commands=["start"])
def starthandler(msg):
    if msg.chat.type != "private":
        bot.send_message(msg.chat.id, f"Your Chat Id: {msg.chat.id}")
        return
    print("here")
    register(str(msg.chat.id))
    bot.send_message(msg.chat.id,
    config.starttext, reply_markup=config.startmarkup)
    if len(msg.text) > 6:
        msg.text = msg.text.replace("/start ", "")
        chatid = msg.text[1:]
        print(msg.text)
        if "/" in msg.text:
            chatid = "-"+msg.text.split("/")[1]
        print(chatid)
        chat = db.session.query(Group).filter_by(
        chat_id=str(chatid)).first()
        if chat is None:
            bot.send_message(msg.chat.id,
            "Group not found!")
        else:
            if "/" in msg.text:
                chatid = msg.text.split("/")[1]
                data = msg.text.split("/")
                t = datetime.datetime.fromtimestamp(int(data[2]))
                info = bot.get_chat(data[1])
                if t < datetime.datetime.now():
                    bot.send_message(msg.chat.id, "Invite link expired")
                    return
                if not is_user_member(data[0]):
                    bot.send_message(msg.chat.id, "You need to be a member of the old chat to use this link!")
                    return
                bot.send_message(msg.chat.id, 
                config.userchattext(chat, info, auto=True), 
                reply_markup=config.userchatmarkup(
                data, auto=True))
                return
            info = bot.get_chat(chatid)
            bot.send_message(msg.chat.id, 
            config.userchattext(chat, info), 
            reply_markup=config.userchatmarkup(
            chatid))


@bot.message_handler(content_types=["text"])
def texthandler(msg):
    if "My Chats" in msg.text:
        chats = db.session.query(Group
        ).filter_by(admin_id=msg.chat.id).all()
        if chats == []:
            bot.send_message(msg.chat.id, "Click ➕ New to add a chat")
        for chat in chats:
            try:
                tginfo = bot.get_chat(chat.chat_id)
                bot.send_message(msg.chat.id, 
                config.mychattext(chat, tginfo),
                reply_markup=config.mychatmarkup(
                    chat.chat_id))
            except:
                bot.send_message(msg.chat.id, "Error!") 
   
       
    elif "New" in msg.text:
        bot.send_message(msg.chat.id, "First add this bot to the group or channel as an admin, with these privileges:")
        bot.copy_message(msg.chat.id, config.storagechatid, config.permissions_photo_id)
        time.sleep(3)
        bot.send_message(msg.chat.id, "Hit \"Done\" when you're finished", 
        reply_markup=config.donecancel)
        bot.register_next_step_handler(msg, new2)
    elif "Support" in msg.text:
        bot.send_message(msg.chat.id, "Please send your questions in one message. They will be forwarded to an admin")
        bot.register_next_step_handler(msg, support)
    elif "My Subscriptions" in msg.text:
        s = get_subscriptions(msg.chat.id)
        if s == []:
            bot.send_message(msg.chat.id, "You have no subscriptions yet")
            return
        else:
            for i in s:
                ginfo = bot.get_chat(i.group.chat_id)
                
                bot.send_message(msg.chat.id,
                config.userchattext(i.group, ginfo), 
                reply_markup=config.userchatmarkup(i.group.chat_id, "unsub"))
    elif "Wallet" in msg.text:
        w = db.session.query(User.wallet).filter_by(
        chat_id=str(msg.chat.id)).first()[0]
        s = db.session.query(Member).filter_by(chat_id=str(msg.chat.id)).all()
        total = 0
        for i in s:
            total += i.group.cost
        bot.send_message(msg.chat.id, f"Your Wallet Balance: {w} USD\n\nYour Subscriptions cost: -${total}", reply_markup=config.walletmarkup)
    elif "Deposit" in msg.text:
        link = payments_api.create_deposit_charge(msg.chat.id)
        if not link:
            bot.send_message(msg.chat.id, "An error occured in generating the payments page. Please contact support")
            return
        bot.send_message(msg.chat.id, f"""
Follow this link to deposit: 
{link}

🔸This link will expire in 1 hour. Generate a new one after that.

🔸The amount you deposit will reflect in your balance in 2-5 minutes.""")
    elif "Withdraw" in msg.text:
        bot.send_message(msg.chat.id, "Enter your Coinbase Gmail or your USDT(Erc20) Ethereum network address", reply_markup=config.cancel)
        bot.register_next_step_handler(msg, withdraw1)
    elif "Cancel" in msg.text or "Back" in msg.text:
        bot.send_message(msg.chat.id, "Main Menu", reply_markup=config.startmarkup)
    else:
        bot.send_message(msg.chat.id, "Not Recognised!", reply_markup=config.startmarkup)
         
 
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    d = call.data
    if "add" in d:
        chatid = d[4:]
        if is_user_subscribed(
        call.from_user.id, chatid):
            bot.send_message(call.from_user.id,
            "You are already subscribed to this Channel")
            return
        if "auto" not in d:
            #Auto will be used for migrating users. add 
            #an elif for that
            r = subscribe_user(
            call.from_user.id,
            chatid)
            if r == 2:
                bot.send_message(call.from_user.id, "Insufficient Funds! Tap on Wallet to deposit some.")
                return
            elif r == 3:
                bot.send_message(call.from_user.id, "An error occured, please contact support.")
                return
            bot.send_message(call.from_user.id, "Processing...")
            
            g = db.session.query(Group).filter_by(
            chat_id=str(chatid)).first()
            if g is None:
                bot.send_message(
                call.from_user.id, "Chat not found!")
                return
            m = Member(
            chat_id=str(call.from_user.id),
            group_chat_id=str(chatid), expiry=str(datetime.date.today()+datetime.timedelta(weeks=4, days=2)))
            g.members.append(m)
            db.session.commit()
            link = bot.create_chat_invite_link(chatid, member_limit=1).invite_link
            bot.send_message(call.from_user.id, f"You were successfully subscribed to the channel! Be sure to maintain enough balance a month from now to stay subscribed. Enjoy the premium experience! Here is your one time link: {link}")
    elif "glink" in d:
        chatid = d.split(":")[1]
        reflink = f"t.me/{config.botusername}?start=g{chatid}"
        bot.send_message(call.from_user.id, f"This link will allow anyone to join after paying for the first month: {reflink}")
    elif "auto" in d:
            o = d.split(':')
            oldgroup=o[1]
            newgroup=o[2]
            if is_user_subscribed(
            call.from_user.id, newgroup):
                bot.send_message(call.from_user.id,
                """You are already subscribed to this Channel""")
                return
            if not is_user_member(
            call.from_user.id,oldgroup):
                bot.send_message(call.from_user.id,
                    """You are not a member of the previous channel, so cannot autojoin the new one. ask the admin to add you back to the old channel and try again.""")
                return
            g = db.session.query(Group).filter_by(
            chat_id=newgroup).first()
            if g is None:
                bot.send_message(call.from_user.id, "Chat not found!")
                return
            m = Member(
            chat_id=str(call.from_user.id),
            group_chat_id=newgroup, expiry=str(datetime.date.today()+datetime.timedelta(days=30)))
            g.members.append(m)
            db.session.commit()
            link = bot.create_chat_invite_link(newgroup, member_limit=1).invite_link
            bot.send_message(call.from_user.id, f"You were successfully subscribed to the channel! Be sure to maintain enough balance a month from now to stay subscribed. Enjoy the premium experience! Here is your one time link: {link}")
      
      
      
    elif "rmv" in d:
        if "rmvno" in d:
            bot.send_message(call.from_user.id, config.starttext, reply_markup=config.startmarkup)
            return
        elif "rmvyes" in d:
            x =unsubscribe_user(
            call.from_user.id, d[7:])
            if not x:
                bot.send_message(call.from_user.id,  "An error occurred! Please contact support.")
                return
            bot.send_message(call.from_user.id,  "You were successfully unsubscribed from the chat")
            return
        bot.send_message(call.from_user.id, "Are you sure you want to unsubscribe from this chat? There will be no refunds! Any fees related to this chat will no longer be taken from your balance", reply_markup=config.yesnomarkup(d[4:]))
        return

    elif "del" in d:
        chatid = d[4:]
        userid=call.from_user.id
        if "delno" in d:
            bot.send_message(call.from_user.id, config.starttext, reply_markup=config.startmarkup)
            return
        elif "delyes" in d:
            x = removechat(
            call.from_user.id, d[7:])
            if x == 3:
                bot.send_message(call.from_user.id,  "You do not have permissions to delete this chat!.")
                return
            bot.send_message(call.from_user.id,  "You successfully removed the chat")
            return
        bot.send_message(call.from_user.id, "Are you sure you want to remove this chat? There will be no more invome from this chat! Any fees related to this chat will no longer be added to your balance", reply_markup=config.yesnomarkup1(chatid))
    elif "refund" in d:
        d = d.split(":")
        user = db.session.query(User).filter_by(chat_id=d[1]).first()
        user.wallet +=float(d[2])
        db.session.commit()
        bot.send_message(d[1], f"An amount of {d[2]} was added to your wallet as a refunded withdrawal. Please try again later or contact support")
        return
    elif "paid" in d:
        d = d.split(":")
        bot.send_message(d[1], f"An amount of {d[2]} was approved and will reflect in your wallet in a few minutes")

@blueprint.route("/triggerdailytasks", methods=["POST"])
def daily_task():
    authorization = request.headers.get("Authorization", "")
    if not hmac.compare_digest(
        authorization, f"Bearer {config.daily_tasks_token}"
    ):
        return "Unauthorized", 401
    ddate = datetime.date.today() + datetime.timedelta(days=2)
    potential_warn = db.session.query(Member).filter_by(expiry = str(ddate)).all()
    # Group subscriptions into a list of lists where each sublist has subscriptions from only one user
    pw2 = collections.defaultdict(lambda:potential_warn)
    for member in potential_warn:
        pw2[member.chat_id].append(member)
    final = pw2.values()
    # Warn users who have subscriptions that expire in 2 days and dont have enough balance
    for user in final:
        total = 0
        for subscription in user:
            total += subscription.cost
        ruser = db.session.query(User).filter_by(chat_id=user[0].chat_id).first()
        if ruser.wallet < total:
            bot.send_message(ruser.chat_id, 
            f"Your current balance is less than what is required to maintain your subscriptions. Please Maintain a balance of over ${total} or unsubscribe from some channels. Some of your subscriptions expire in 2 day")
            continue
        continue
    # Unsub users who do not have enough balance to cover their subscriptions and deduct from those who do
    potential_remove = db.session.query(Member).filter_by(expiry = str(datetime.date.today())).all()
    for member in potential_remove:
        user = db.session.query(User).filter_by(chat_id=member.chat_id).first()
        if user.wallet < member.group.cost:
            gid = member.group.chat_id
            unsubscribe_user(user.chat_id, member.group.chat_id)
            chat = bot.get_chat(gid)
            bot.send_message(user.chat_id, f"You were unsubscribed from {chat.title} due to insufficient balance")
            continue
        else:
            chat = bot.get_chat(member.group.chat_id)
            settle_payment(user, member.group.user, member.group)
            bot.send_message(user.chat_id, f"An amount of ${member.group.cost} was used to renew your subscription to {chat.title}")
            continue
    return "Ok Done!", 200
