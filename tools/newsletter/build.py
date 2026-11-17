"""Builds the Dejoiy Mail newsletter mock: preview.html (local image paths) and send.html (cid: images)."""
import sys

INK, PINK, CREAM = "#121212", "#FF4FA3", "#FFF4EA"
FONT = "'Helvetica Neue',Helvetica,Arial,sans-serif"
SIGNUP = "https://mail.dejoiy.com/signup"


BASE = "https://mail.dejoiy.com/assets/newsletter/"


def build(cid, base=""):
    src = (lambda n: f"cid:{n.split('.')[0]}") if cid else (lambda n: base + n)

    def img(n, alt, w=600, h=None):
        hh = f' height="{h}"' if h else ''
        return (f'<tr><td style="padding:0;line-height:0;font-size:0"><img src="{src(n)}" width="{w}"{hh} alt="{alt}" '
                f'style="display:block;width:100%;max-width:{w}px;height:auto;border:0"></td></tr>')

    def text(bg, fg, html, pad="14px 32px 36px"):
        return (f'<tr><td style="background:{bg};color:{fg};padding:{pad};font:16px/1.6 {FONT}">{html}</td></tr>')

    def p(t, fg=None):
        c = f'color:{fg};' if fg else ''
        return f'<p style="margin:0 0 14px;{c}">{t}</p>'

    def button(label, bg, fg):
        return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-top:8px"><tr>'
                f'<td style="background:{bg};border-radius:999px"><a href="{SIGNUP}" style="display:inline-block;padding:15px 28px;'
                f'font:700 16px {FONT};color:{fg};text-decoration:none;border-radius:999px">{label} &rarr;</a></td></tr></table>')

    def plan(name, month, year, seats, hot=False):
        bg, fg, sub = (PINK, INK, INK) if hot else (INK, CREAM, "#c9c2bb")
        return (f'<tr><td style="padding:0 0 10px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
                f'style="background:{bg};border-radius:18px"><tr>'
                f'<td style="padding:18px 20px;font:800 22px/1.1 {FONT};color:{fg}">{name}'
                f'<div style="font:400 14px/1.4 {FONT};color:{sub};padding-top:4px">{seats}</div></td>'
                f'<td align="right" style="padding:18px 20px;font:800 22px/1.1 {FONT};color:{fg};white-space:nowrap">{month}<span style="font-weight:400;font-size:14px">/mo</span>'
                f'<div style="font:400 14px/1.4 {FONT};color:{sub};padding-top:4px">or {year}/yr</div></td>'
                f'</tr></table></td></tr>')

    rows = [
        img("hero.gif", "Dejoiy Mail: company mail that finally feels like you.", 600, 560),
        text(INK, CREAM,
             p("Hi {{first_name}},")
             + p("Dejoiy Mail is business email on your own domain, made by DEJOIY in New Delhi. "
                 "You pay one flat price for the whole company, not a fee for every person who joins.")
             + p("Here is what's inside.")
             + button("Start your 11-day trial", PINK, INK), "28px 32px 40px"),
        img("h_domain.png", "Your domain. Your whole inbox."),
        img("laptop.jpg", "Dejoiy Mail inbox on a laptop, dark theme"),
        text(CREAM, INK,
             p("Mail at <b>you@yourcompany.com</b>, with calendar, contacts and booking links that let clients pick a slot themselves.")
             + p("Undo send, auto-reply, filters and automations are built in. Mail that looks like phishing or spam gets a clear mark before anyone clicks.")),
        img("h_look.png", "Make it look like you."),
        img("phone.gif", "Dejoiy Mail on a phone, switching between light, dark and galaxy themes"),
        text(PINK, INK,
             p("Light, dark, galaxy, or your own photo behind the inbox. Each person picks their own.")
             + p("On a phone it opens in the browser and can be added to the home screen. Sign-in works with a passkey, "
                 "and one person can switch between several accounts.")),
        img("h_roles.png", "Who can do what? You decide."),
        img("admin.jpg", "Dejoiy Mail Admin console showing the mailboxes list"),
        text(INK, CREAM,
             p("The admin console comes with <b>18 ready-made roles</b>, from Super Administrator to Guest, plus your own custom roles.")
             + p("Give a role to the whole company, one department or a few people, and for a fixed time if you want. "
                 "Turn off <b>sending outside the company</b> for one person; they can ask their admin, and you approve in one click.")
             + p("Nobody can approve their own request or read someone else's mail on their own, "
                 "and every change goes into an access log that cannot be edited.", "#c9c2bb")
             + p("Your logo, company name and sign-in background go on every screen.")),
        img("h_swiss.png", "Mail that actually lands."),
        text(CREAM, INK,
             p("The admin console shows the exact SPF, DKIM and DMARC records your domain needs, and tells you which ones are live.")
             + p("Sending a lot? The <b>Swiss Mail add-on</b> sends up to 10,000 mails a month from your own domain through "
                 "Dejoiy Swiss Mail, our sending service on Amazon SES. It costs &#8377;199 a month plus GST.")
             + p("No provider can promise every single inbox. Correct records and a clean sending service give your mail its best chance, "
                 "and that is what you get here.", "#5a524c")),
        img("h_desk.png", "Help desk, Joi and Shine. Included."),
        img("desk.jpg", "Dejoiy Mail help desk ticket on a laptop"),
        text(PINK, INK,
             p("Turn mail into help desk tickets with owners, priority and private team notes.")
             + p("<b>Joi</b>, our AI assistant, helps write and summarise mail right where you work. "
                 "<b>Shine</b> adds team chat, calls and meetings for everyone, included in every plan.")),
        img("h_move.png", "Moving? That's on us."),
        text(INK, CREAM,
             p("Already on Gmail, Google Workspace or Zoho? Our team moves your existing mail and sets up your mailboxes for you, at no charge.")
             + p("You keep working while it happens. Reply to this mail and we'll plan the move with you.", "#c9c2bb")),
        img("h_plans.png", "One price. Whole company."),
        f'<tr><td style="background:{CREAM};padding:14px 32px 8px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        + plan("Starter", "&#8377;99", "&#8377;790", "Up to 51 mailboxes")
        + plan("Team", "&#8377;299", "&#8377;2,490", "Up to 101 mailboxes", True)
        + plan("Business", "&#8377;699", "&#8377;5,990", "Unlimited mailboxes")
        + '</table></td></tr>',
        text(CREAM, INK,
             p("Prices are for the whole company, plus 18% GST. Shine is included. Pay with UPI AutoPay or a card through Dejoiy Pay.", "#5a524c")
             + button("Start your 11-day trial", INK, CREAM), "6px 32px 40px"),
        text(INK, CREAM,
             p("Questions? Just reply. A real person reads every one.")
             + p("<b>Deepak Sharma</b><br>DEJOIY", "#FFF4EA"), "36px 32px 20px"),
        f'<tr><td style="background:{INK};padding:8px 32px 36px;font:13px/1.6 {FONT};color:#9a938d">'
        f'<img src="{src("logo.png")}" width="164" height="32" alt="Dejoiy Mail" style="display:block;border:0;margin:0 0 16px">'
        'Dejoiy India Private Limited, New Delhi<br>'
        '<span style="background:#3a2a32;color:#FF4FA3;padding:1px 6px;border-radius:4px">[postal address: to be added before sending]</span><br><br>'
        'Not interested? Reply "no thanks" and we won\'t email you again.</td></tr>',
    ]
    pre = ("One flat price for your whole company: your domain, roles, help desk and team chat in one place."
           + "&#847;&zwnj;&nbsp;" * 40)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><title>Dejoiy Mail: company mail that finally feels like you</title>
<style>@media (max-width:620px){{.wrap{{width:100%!important}}}}</style></head>
<body style="margin:0;padding:0;background:#2b2b2b">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{pre}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#2b2b2b"><tr><td align="center" style="padding:24px 0">
<table role="presentation" class="wrap" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;background:{INK};border-radius:24px;overflow:hidden">
{''.join(rows)}
</table></td></tr></table></body></html>"""


if __name__ == "__main__":
    open("preview.html", "w").write(build(False))
    open("send.html", "w").write(build(True))
    open("issue-01.html", "w").write(build(False, BASE))
    print(len(build(True).encode()), "bytes")
