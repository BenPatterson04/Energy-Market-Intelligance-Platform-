import os

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)

from services.weather import get_weather
from services.markets import get_markets, get_market_history
from services.domestic import get_domestic_prices
from services.uk_news import get_uk_news
from services.global_news import get_global_news
from services.grid import get_grid_status, get_full_generation_mix
from services import electricitymaps as isem
from services import history
from services import ai_commentary
from services import forecasts
from services import auth
from services import billing
from services import octopus

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or "dev-only-change-this-before-deploying"

history.init_db()
auth.init_db()

login_manager = LoginManager(app)
login_manager.login_view = "login_page"


@login_manager.user_loader
def load_user(user_id):
    return auth.get_user_by_id(user_id)


DASHBOARD_TEMPLATES = {
    "business": "dashboard_business.html",
    "student": "dashboard_student.html",
    "domestic": "dashboard_domestic.html",
}


def _gather_common_data(account_type=None):
    return {
        "weather": get_weather(),
        "markets": get_markets(),
        "domestic": get_domestic_prices(),
        "grid": get_grid_status(),
        "uk_news": get_uk_news(account_type=account_type),
        "global_news": get_global_news(account_type=account_type),
        "isem": isem.get_isem_snapshot(region="ALL"),
    }


def _safe_num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register_page():

    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        account_type = request.form.get("account_type")

        if not name or not email or not password or account_type not in auth.VALID_ACCOUNT_TYPES:
            return render_template("register.html", error="Please fill in every field and pick an account type.")

        if len(password) < 8:
            return render_template("register.html", error="Password must be at least 8 characters.")

        try:
            user_id = auth.create_user(email, password, name, account_type)
        except ValueError as e:
            return render_template("register.html", error=str(e))

        user = auth.get_user_by_id(user_id)
        login_user(user)
        return redirect(url_for("home"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login_page():

    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        user = auth.verify_login(email, password)

        if user is None:
            return render_template("login.html", error="Incorrect email or password.")

        login_user(user)
        return redirect(url_for("home"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout_page():
    logout_user()
    return redirect(url_for("login_page"))


# ---------------------------------------------------------------
# Billing routes
# ---------------------------------------------------------------

@app.route("/upgrade")
@login_required
def upgrade_page():
    return render_template("upgrade.html", price=billing.get_premium_price_display())


@app.route("/billing/checkout", methods=["POST"])
@login_required
def billing_checkout():
    try:
        checkout_url = billing.create_checkout_session(
            user=current_user,
            success_url=url_for("home", _external=True),
            cancel_url=url_for("upgrade_page", _external=True),
        )
        return redirect(checkout_url)
    except Exception as e:
        flash(f"Checkout failed: {e}")
        return redirect(url_for("upgrade_page"))


@app.route("/billing/portal")
@login_required
def billing_portal():
    try:
        portal_url = billing.create_portal_session(
            user=current_user,
            return_url=url_for("upgrade_page", _external=True),
        )
        return redirect(portal_url)
    except Exception as e:
        flash(f"Couldn't open billing portal: {e}")
        return redirect(url_for("upgrade_page"))


@app.route("/billing/webhook", methods=["POST"])
def billing_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")
    status_code, message = billing.handle_webhook(payload, sig_header)
    return jsonify({"message": message}), status_code


# ---------------------------------------------------------------
# Main app routes (all require login)
# ---------------------------------------------------------------

from functools import wraps


def admin_required(func):
    """Blocks non-admin users with a 403, rather than silently redirecting -
    an admin page returning 403 to a regular member is expected behavior,
    not a bug to hide."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return "Forbidden - admin access only", 403
        return func(*args, **kwargs)

    return wrapper


@app.route("/admin")
@login_required
@admin_required
def admin_page():
    price_info = billing.get_premium_price_display()
    premium_price = float(price_info["amount"]) if price_info else 0

    return render_template(
        "admin.html",
        members=auth.get_all_users(),
        stats=auth.get_member_stats(premium_price_gbp=premium_price),
        price_configured=price_info is not None,
    )


@app.route("/")
@login_required
def home():

    # Dev/demo convenience: ?preview=business|student|domestic lets your
    # own account see any of the three dashboards without needing three
    # separate logins. It only changes which template renders for this
    # one request - it does NOT change your actual account_type in the
    # database, so your tier/premium status still applies correctly for
    # whichever view you're previewing. Resolved BEFORE gathering data so
    # the news feed is also relevant to whichever dashboard is showing.
    preview = request.args.get("preview")
    account_type = preview if preview in DASHBOARD_TEMPLATES else current_user.account_type

    data = _gather_common_data(account_type=account_type)

    template = DASHBOARD_TEMPLATES.get(account_type, "dashboard_domestic.html")

    return render_template(
        template,
        weather=data["weather"],
        markets=data["markets"],
        domestic=data["domestic"],
        grid=data["grid"],
        isem=data["isem"],
        news={"uk": data["uk_news"], "global": data["global_news"]},
        dashboard_audience=account_type,
    )


@app.route("/markets")
@login_required
def markets_page():
    data = _gather_common_data()
    return render_template("markets.html", markets=data["markets"])


@app.route("/api/market-history")
@login_required
def api_market_history():
    symbol = request.args.get("symbol", "BZ=F")
    days = int(request.args.get("days", 30))
    return jsonify(get_market_history(symbol, days=days))


@app.route("/grid")
@login_required
def grid_page():
    data = _gather_common_data()
    return render_template("grid.html", grid=data["grid"])


@app.route("/api/grid-generation-mix")
@login_required
def api_grid_generation_mix():
    return jsonify(get_full_generation_mix())


@app.route("/domestic")
@login_required
def domestic_page():
    data = _gather_common_data()
    return render_template("domestic.html", domestic=data["domestic"])


@app.route("/api/agile-rates")
@login_required
def api_agile_rates():
    return jsonify(octopus.get_agile_rates_today())


@app.route("/intelligence")
@login_required
def intelligence_page():
    data = _gather_common_data()
    return render_template(
        "intelligence.html",
        news={"uk": data["uk_news"], "global": data["global_news"]},
    )


@app.route("/forecasts")
@login_required
def forecasts_page():
    return render_template("forecasts.html")


@app.route("/api/forecast-data")
@login_required
def api_forecast_data():
    region = request.args.get("region", "ALL")
    return jsonify(forecasts.get_demand_wind_projection(region=region))


@app.route("/about")
def about_page():
    return render_template("about.html")


@app.route("/isem")
@login_required
def isem_page():
    """Version 4: dedicated i-SEM market page with Plotly charts + grid map."""

    data = _gather_common_data()

    return render_template(
        "isem.html",
        isem=data["isem"],
        grid=data["grid"],
        watchlist=history.get_watchlist(),
        alerts=history.get_alerts(active_only=True),
        alert_log=history.get_recent_alert_log(limit=10),
    )


@app.route("/api/isem-history")
@login_required
def api_isem_history():
    """JSON feed consumed by Plotly on the frontend."""

    region = request.args.get("region", "ALL")
    hours = int(request.args.get("hours", 24))

    return jsonify(isem.get_isem_chart_data(region=region, hours=hours))


@app.route("/api/grid-map")
@login_required
def api_grid_map():
    return jsonify(isem.get_grid_map_data())


@app.route("/api/commentary")
@login_required
def api_commentary():
    """AI briefing, generated on demand. audience=business|student|domestic -
    defaults to the logged-in user's own account_type if not specified."""

    audience = request.args.get("audience") or current_user.account_type
    data = _gather_common_data(account_type=audience)

    text = ai_commentary.generate_commentary(
        markets=data["markets"],
        isem=data["isem"],
        grid=data["grid"],
        news={"uk": data["uk_news"], "global": data["global_news"]},
        audience=audience,
        domestic=data["domestic"],
    )

    return jsonify({"audience": audience, "commentary": text})


@app.route("/api/watchlist", methods=["GET", "POST", "DELETE"])
@login_required
def api_watchlist():

    if request.method == "GET":
        return jsonify(history.get_watchlist())

    payload = request.get_json(force=True, silent=True) or {}
    item_key = payload.get("item_key")

    if request.method == "POST":
        history.add_watchlist_item(
            item_key=item_key,
            label=payload.get("label", item_key),
            category=payload.get("category", "market"),
        )
        return jsonify({"status": "added", "item_key": item_key})

    if request.method == "DELETE":
        history.remove_watchlist_item(item_key)
        return jsonify({"status": "removed", "item_key": item_key})


@app.route("/api/alerts", methods=["GET", "POST"])
@login_required
def api_alerts():

    if request.method == "GET":
        return jsonify(history.get_alerts())

    payload = request.get_json(force=True, silent=True) or {}

    alert_id = history.add_alert(
        metric=payload["metric"],
        label=payload.get("label", payload["metric"]),
        condition=payload["condition"],
        threshold=float(payload["threshold"]),
    )

    return jsonify({"status": "created", "alert_id": alert_id})


@app.route("/api/alerts/<int:alert_id>", methods=["DELETE"])
@login_required
def api_delete_alert(alert_id):
    history.deactivate_alert(alert_id)
    return jsonify({"status": "deactivated", "alert_id": alert_id})


if __name__ == "__main__":
    app.run(debug=True)
