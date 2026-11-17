import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data_utils import NAMES, clean, load_raw, window_metrics, winners, yearly_metrics

st.set_page_config(layout="wide", page_title="Which index won?")

PALETTE = px.colors.qualitative.Plotly
COLORS = {name: PALETTE[i] for i, name in enumerate(NAMES.values())}   # same color per index everywhere


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
start, end = st.sidebar.slider("Time window", d0, d1, (d0, d1))
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

# ---- row 1: rebased prices + Return/Vol ranking
c1, c2 = st.columns(2)
rebased = (w[sel] / w[sel].iloc[0] * 100).rename(columns=NAMES)
c1.plotly_chart(px.line(rebased, title="Rebased to 100 at window start",
                        color_discrete_map=COLORS), width="stretch")

mm = m.sort_values("Return/Vol", ascending=False)      # highest first
hb = px.bar(mm, x="Return/Vol", y="Index", orientation="h", color="Index",
            color_discrete_map=COLORS, text=mm["Return/Vol"].map("{:.2f}".format),
            category_orders={"Index": list(mm["Index"])},
            title="Return/Vol over the selected window (highest on top)")
hb.update_layout(showlegend=False, yaxis_title=None)
c2.plotly_chart(hb, width="stretch")

# ---- row 2: return heatmap + volatility bump chart
st.subheader("Year by year")
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

# ---- row 3: yearly return vs. risk + best years
c5, c6 = st.columns(2)
sc = px.scatter(yt, x="Volatility", y="Return", color="Index", hover_name="Year",
                color_discrete_map=COLORS,
                title="Each year: return vs. risk (one dot per index per year)")
sc.update_traces(marker=dict(size=11))
sc.update_xaxes(tickformat=".0%")
sc.update_yaxes(tickformat=".0%")
c5.plotly_chart(sc, width="stretch")

best = (yt.sort_values("Return", ascending=False).groupby("Index").head(3)
          .sort_values(["Index", "Return"], ascending=[True, False])[["Index", "Year", "Return"]])
c6.subheader("Top 3 years by return, per index")
c6.dataframe(best.style.format({"Return": "{:.1%}"}), hide_index=True)

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

st.subheader("Window metrics")
st.dataframe(m.style.format({"Total return": "{:.1%}", "Ann. return": "{:.1%}",
                             "Ann. volatility": "{:.1%}", "Return/Vol": "{:.2f}",
                             "Max drawdown": "{:.1%}"}), hide_index=True)

st.caption("Source: FRED (St. Louis Fed). Index data belongs to its publishers "
           "(S&P Dow Jones Indices, Nasdaq). Price-only, no dividends.")