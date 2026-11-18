import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from data_utils import NAMES, clean, load_raw, window_metrics, winners, yearly_metrics

st.set_page_config(layout="wide", page_title="Which index won?")

PALETTE = px.colors.qualitative.Plotly
COLORS = {name: PALETTE[i] for i, name in enumerate(NAMES.values())}   # same color per index everywhere

# Bar order toggle: if the highest Return/Vol bar is at the BOTTOM, change this to True.
REVERSE_BARS = False

WF_LABEL_SIZE = 14    # font size of the numbers above the waterfall bars
BASE = 10_000         # hypothetical amount invested at window start
LABEL_IN_K = True     # True: labels like +2.4k; False: labels like +2,400 (hover always shows full)


@st.cache_data(ttl=24 * 3600, show_spinner="Loading index data...")
def get_data():
    raw, source = load_raw()
    return clean(raw), source


def card(col, label, name, value):
    col.markdown(
        f"""<div style="padding:12px 16px;border:1px solid #ccc;border-radius:10px;">
        <div style="font-size:0.95rem;opacity:0.7;">{label}</div>
        <div style="font-size:1.7rem;font-weight:700;">{name}</div>
        <div style="font-size:2.4rem;font-weight:700;line-height:1.1;">{value}</div>
        </div>""", unsafe_allow_html=True)


def signed(v):
    return f"{v:+,.0f}"                  # +2,400 or -1,200 (used in hover text)


def bar_label(v):
    return f"{v / 1000:+.1f}k" if LABEL_IN_K else signed(v)


try:
    df, source = get_data()
except Exception as e:
    st.error(f"Could not load the index data ({type(e).__name__}): {e}")
    st.stop()

st.title("Which index won, and does the answer depend on the window?")
st.caption(f"Price-only index levels (no dividends). Data: {source}. "
           "Return/Vol = annualized mean daily return ÷ annualized volatility.")
st.caption(f"Data range: {df.index.min().date()} to {df.index.max().date()} "
           f"({len(df):,} trading days)")

# ---- controls
d0, d1 = df.index.min().date(), df.index.max().date()
H = {"1Y": 252, "3Y": 756, "5Y": 1260}      # trading-day approximations of 1, 3, 5 years

if "win" not in st.session_state:           # must be set before the slider is created
    st.session_state["win"] = (d0, d1)
    st.session_state["win_note"] = ""


def set_window(start, end, note=""):
    st.session_state["win"] = (start.date(), end.date())
    st.session_state["win_note"] = note


def go_last(label):
    n = H[label]
    set_window(df.index[max(0, len(df) - 1 - n)], df.index[-1], f"Last {label}")


def go_all():
    set_window(df.index[0], df.index[-1], "")


def go_weakest(label):
    c, n = st.session_state["worst_idx"], H[label]
    if len(df) <= n:
        return
    r = df[c].pct_change(n)                  # trailing n-day total return
    end_ = r.idxmin()
    start_ = df.index[df.index.get_loc(end_) - n]
    set_window(start_, end_, f"Weakest {label} window for {NAMES[c]}: "
                             f"{start_.date()} to {end_.date()} ({r.min():.1%})")


# 1. Time window
start, end = st.sidebar.slider("Time window", min_value=d0, max_value=d1, key="win")
if st.session_state["win_note"]:
    st.sidebar.caption(st.session_state["win_note"])

# 2. Quick windows
st.sidebar.markdown("**Quick windows**")
cols = st.sidebar.columns(4)
for col, lab in zip(cols[:3], H):
    col.button(f"Last {lab}", on_click=go_last, args=(lab,), key=f"last_{lab}")
cols[3].button("All", on_click=go_all, key="all")

# 3. Jump to an index's weakest window
st.sidebar.markdown("**Jump to an index's weakest window**")
st.sidebar.selectbox("Index", list(NAMES), format_func=NAMES.get, key="worst_idx")
cols = st.sidebar.columns(3)
for col, lab in zip(cols, H):
    col.button(f"{lab}", on_click=go_weakest, args=(lab,), key=f"weak_{lab}")

# 4. Indices
sel = st.sidebar.multiselect("Indices", list(NAMES), default=list(NAMES),
                             format_func=NAMES.get)

if len(sel) < 2 or (pd.Timestamp(end) - pd.Timestamp(start)).days < 90:
    st.warning("Pick at least 2 indices and a window of 3+ months.")
    st.stop()

w = df.loc[pd.Timestamp(start):pd.Timestamp(end)]
m = window_metrics(w, sel)
yt = yearly_metrics(w, sel)

# ---- headline cards
k1, k2, k3, k4 = st.columns(4)
a = m.loc[m["Total return"].idxmax()]
b = m.loc[m["Ann. volatility"].idxmax()]
c = m.loc[m["Return/Vol"].idxmax()]
d = m.loc[m["Max drawdown"].idxmin()]
card(k1, "Highest return", a["Index"], f"{a['Total return']:.1%}")
card(k2, "Most volatile", b["Index"], f"{b['Ann. volatility']:.1%}")
card(k3, "Best Return/Vol", c["Index"], f"{c['Return/Vol']:.2f}")
card(k4, "Deepest drawdown", d["Index"], f"{d['Max drawdown']:.1%}")

# ---- row 1: price growth + risk-adjusted performance
c1, c2 = st.columns(2)
rebased = (w[sel] / w[sel].iloc[0] * 100).rename(columns=NAMES)
line = px.line(rebased, title="Price Growth Over Time", color_discrete_map=COLORS)
line.update_layout(legend_title_text=None, xaxis_title=None, yaxis_title="Index level")
c1.plotly_chart(line, width="stretch")
c1.caption("Rebased to 100 at window start.")

mm = m.sort_values("Return/Vol", ascending=False)      # highest first
hb = px.bar(mm, x="Return/Vol", y="Index", orientation="h", color="Index",
            color_discrete_map=COLORS, text=mm["Return/Vol"].map("{:.2f}".format),
            category_orders={"Index": list(mm["Index"])},
            title="Risk-Adjusted Performance (Return/Volatility)")
hb.update_layout(showlegend=False, yaxis_title=None)
if REVERSE_BARS:
    hb.update_yaxes(autorange="reversed")
c2.plotly_chart(hb, width="stretch")

# ---- row 2: return heatmap + volatility bump chart
st.subheader("Year by year")
if (end - start).days < 800:
    st.caption("Short window: year-by-year views include partial years (*) and are thin.")
c3, c4 = st.columns(2)

years = list(dict.fromkeys(yt["Year"]))                 # chronological, partial years keep the *
heat = (yt.pivot(index="Index", columns="Year", values="Return")
          .reindex(index=[NAMES[x] for x in sel], columns=years))
zmax = float(heat.abs().max().max())
hm = go.Figure(go.Heatmap(
    z=heat.values, x=years, y=list(heat.index),
    zmin=-zmax, zmax=zmax,
    colorscale=[[0, "#d73027"], [0.5, "#ffffff"], [1, "#1a9850"]],   # red = negative, green = positive
    text=heat.values, texttemplate="%{z:.0%}",
    textfont=dict(size=13, color="black"),
    xgap=2, ygap=2, colorbar=dict(tickformat=".0%")))
hm.update_xaxes(type="category")
hm.update_yaxes(autorange="reversed")
hm.update_layout(title="Calendar-year price return (* = partial year)")
c3.plotly_chart(hm, width="stretch")

bump = px.line(yt, x="Year", y="Vol rank", color="Index", markers=True,
               color_discrete_map=COLORS,
               title="Volatility rank by year (1 = most volatile)")
bump.update_yaxes(autorange="reversed", dtick=1)
bump.update_xaxes(type="category")
c4.plotly_chart(bump, width="stretch")

# ---- row 3: return vs risk scatter + summary metrics
c5, c6 = st.columns(2)
sc = px.scatter(yt, x="Volatility", y="Return", color="Index", hover_name="Year",
                color_discrete_map=COLORS,
                title="Return vs Risk (one dot per index per year)")
sc.update_traces(marker=dict(size=11))
sc.update_xaxes(tickformat=".0%")
sc.update_yaxes(tickformat=".0%")
c5.plotly_chart(sc, width="stretch")

c6.subheader("Summary Metrics")
c6.dataframe(m.style.format({"Total return": "{:.1%}", "Ann. return": "{:.1%}",
                             "Ann. volatility": "{:.1%}", "Return/Vol": "{:.2f}",
                             "Max drawdown": "{:.1%}"}), hide_index=True)

# ---- row 4: waterfall (full width so labels have room)
names = [NAMES[x] for x in sel]
ncols = 2
nrows = -(-len(names) // ncols)
wf = make_subplots(rows=nrows, cols=ncols, subplot_titles=names,
                   vertical_spacing=0.22, horizontal_spacing=0.06)

for i, nm in enumerate(names):
    r_, c_ = i // ncols + 1, i % ncols + 1
    g = yt[yt["Index"] == nm]
    value = BASE * (1 + g["Return"]).cumprod()         # growth of the hypothetical investment at each year-end
    prev = value.shift(1).fillna(BASE)
    gain = value - prev                                # dollars added that year
    total = value.iloc[-1] - BASE

    xs = list(g["Year"]) + ["Total"]

    # bars only (no built-in text; labels are drawn separately below)
    wf.add_trace(go.Waterfall(
        x=xs,
        y=list(gain) + [0],
        measure=["relative"] * len(g) + ["total"],
        hovertext=[f"{signed(v)} ({r:.1%} return)" for v, r in zip(gain, g["Return"])]
                  + [f"{signed(total)} total gain"],
        hoverinfo="x+text",
        increasing=dict(marker=dict(color="#1a9850")),
        decreasing=dict(marker=dict(color="#d73027")),
        totals=dict(marker=dict(color="#555555")),
        connector=dict(line=dict(width=1)),
    ), row=r_, col=c_)

    # labels: a text-only layer placed at the top of each bar, all the same font size
    tops = list(pd.concat([prev - BASE, value - BASE], axis=1).max(axis=1)) + [max(total, 0)]
    labels = [bar_label(v) for v in gain] + [bar_label(total)]
    wf.add_trace(go.Scatter(
        x=xs, y=tops, mode="text",
        text=[f"<b>{t}</b>" for t in labels],
        textposition="top center",
        textfont=dict(size=WF_LABEL_SIZE),
        hoverinfo="skip", showlegend=False,
    ), row=r_, col=c_)

    # headroom so labels aren't clipped
    lo = min(0, float((value - BASE).min()), float(total))
    hi = max(max(tops), 0)
    span = (hi - lo) or 1
    wf.update_yaxes(range=[lo - 0.08 * span, hi + 0.22 * span], row=r_, col=c_)

wf.update_layout(title=f"Hypothetical gain per year on ${BASE:,.0f} invested at window start",
                 showlegend=False, height=380 * nrows + 100)
wf.update_xaxes(type="category", tickangle=-45)
wf.update_yaxes(tickprefix="$", tickformat=",.0f")     # the only place a $ appears on the bars
st.plotly_chart(wf, width="stretch")
st.caption(f"Each bar is the change in the value of a hypothetical ${BASE:,.0f} invested at the start "
           "of the selected window. The grey bar is the total gain. "
           + ("Labels are in thousands of dollars (k). " if LABEL_IN_K else "")
           + "Price-only: no dividends, taxes, or fees.")

# ---- tables
st.subheader("Year-by-year winners")
st.caption("Winner = best Return/Vol that year. Single-year ratios are noisy; "
           "margins under ~1.0 are within the noise (rough rule of thumb).")
st.dataframe(winners(yt).style.format({
    "Return": "{:.1%}", "Volatility": "{:.1%}", "Return/Vol": "{:.2f}",
    "Margin over 2nd": "{:.2f}", "Best return value": "{:.1%}"}), hide_index=True)

with st.expander("All years, all indices"):
    st.dataframe(yt[["Year", "Index", "Days", "Return", "Volatility", "Return/Vol",
                     "Ratio rank", "Vol rank"]]
                 .style.format({"Return": "{:.1%}", "Volatility": "{:.1%}",
                                "Return/Vol": "{:.2f}"}), hide_index=True)

st.caption("Source: FRED (St. Louis Fed). Index data belongs to its publishers "
           "(S&P Dow Jones Indices, Nasdaq). Price-only, no dividends.")