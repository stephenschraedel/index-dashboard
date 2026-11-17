import pandas as pd
import plotly.express as px
import streamlit as st

from data_utils import NAMES, clean, load_raw, window_metrics, winners, yearly_metrics

st.set_page_config(layout="wide", page_title="Which index won?")


@st.cache_data(ttl=24 * 3600, show_spinner="Loading index data...")
def get_data():
    raw, source = load_raw()
    return clean(raw), source


try:
    df, source = get_data()
except Exception as e:
    st.error(f"Could not load the index data ({type(e).__name__}): {e}")
    st.info("The data is fetched live from FRED, with a stored snapshot as a fallback. "
            "Please try again later.")
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

w = df.loc[pd.Timestamp(start):pd.Timestamp(end)]     # everything below uses this window
m = window_metrics(w, sel)
yt = yearly_metrics(w, sel)

# ---- headline answers for the selected window
k1, k2, k3, k4 = st.columns(4)
r = m.loc[m["Total return"].idxmax()]
v = m.loc[m["Ann. volatility"].idxmax()]
q = m.loc[m["Return/Vol"].idxmax()]
d = m.loc[m["Max drawdown"].idxmin()]
k1.metric("Highest return", r["Index"], f"{r['Total return']:.1%}")
k2.metric("Most volatile", v["Index"], f"{v['Ann. volatility']:.1%} ann. vol", delta_color="off")
k3.metric("Best Return/Vol", q["Index"], f"{q['Return/Vol']:.2f}")
k4.metric("Deepest drawdown", d["Index"], f"{d['Max drawdown']:.1%}", delta_color="off")

# ---- row 1: rebased prices + risk vs return
c1, c2 = st.columns(2)
rebased = (w[sel] / w[sel].iloc[0] * 100).rename(columns=NAMES)
c1.plotly_chart(px.line(rebased, title="Rebased to 100 at window start"),
                use_container_width=True)
c2.plotly_chart(px.scatter(m, x="Ann. volatility", y="Ann. return", color="Index",
                           size=[20] * len(m),
                           title="Risk vs. return (steeper line from origin = better Return/Vol)"),
                use_container_width=True)

# ---- row 2: heatmap + bump chart
st.subheader("Year by year")
c3, c4 = st.columns(2)
heat = yt.pivot(index="Index", columns="Year", values="Return/Vol")
c3.plotly_chart(px.imshow(heat, text_auto=".2f", aspect="auto",
                          color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
                          title="Return/Vol by calendar year (* = partial year)"),
                use_container_width=True)

bump = px.line(yt, x="Year", y="Ratio rank", color="Index", markers=True,
               title="Return/Vol rank by year (1 = best)")
bump.update_yaxes(autorange="reversed", dtick=1)
bump.update_xaxes(type="category")
c4.plotly_chart(bump, use_container_width=True)

# ---- row 3: annual returns + best years
c5, c6 = st.columns(2)
bar = px.bar(yt, x="Year", y="Return", color="Index", barmode="group",
             title="Calendar-year price return")
bar.update_yaxes(tickformat=".0%")
c5.plotly_chart(bar, use_container_width=True)

best = (yt.sort_values("Return", ascending=False).groupby("Index").head(3)
          .sort_values(["Index", "Return"], ascending=[True, False])[["Index", "Year", "Return"]])
c6.subheader("Top 3 years by return, per index")
c6.dataframe(best.style.format({"Return": "{:.1%}"}), hide_index=True)

# ---- tables
st.subheader("Year-by-year winners")
st.caption("Single-year ratios are noisy. Margins under ~1.0 are within the noise (rough rule of thumb).")
st.dataframe(winners(yt).style.format({"Margin over 2nd": "{:.2f}"}), hide_index=True)

st.subheader("Window metrics")
st.dataframe(m.style.format({"Total return": "{:.1%}", "Ann. return": "{:.1%}",
                             "Ann. volatility": "{:.1%}", "Return/Vol": "{:.2f}",
                             "Max drawdown": "{:.1%}"}), hide_index=True)

st.caption("Source: FRED (St. Louis Fed). Index data belongs to its publishers "
           "(S&P Dow Jones Indices, Nasdaq). Price-only, no dividends.")