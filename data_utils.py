from pathlib import Path
import numpy as np
import pandas as pd

TD = 252
PARTIAL_DAYS = 240          # judgment call: years with fewer days get a "*"
MIN_DAYS = 2000             # judgment call: ~8 years; fewer rows = failed load
MAX_START_GAP_DAYS = 45     # index series must start within ~6 weeks of each other
START = pd.Timestamp.today().normalize() - pd.DateOffset(years=10)
SNAPSHOT = Path("data/fred_snapshot.csv")

SERIES = {"SP500": "sp500", "NASDAQCOM": "nasdaq", "NASDAQ100": "ndx",
          "DJIA": "djia", "DGS10": "y10"}   # y10 unused so far
NAMES = {"sp500": "S&P 500", "nasdaq": "NASDAQ Composite",
         "ndx": "NASDAQ-100", "djia": "DJIA"}


def _numeric(raw):
    """Force numeric dtypes; FRED's '.' and any other text become NaN."""
    return raw.apply(pd.to_numeric, errors="coerce")


def fetch_fred():
    cols = []
    for sid, name in SERIES.items():
        s = pd.read_csv(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}",
                        index_col=0, parse_dates=True, na_values=".")
        s.columns = [name]
        cols.append(s)
    raw = pd.concat(cols, axis=1)
    return _numeric(raw.loc[raw.index >= START])


def check_coverage(raw):
    """Fail loudly if any index series is short or starts much later than the rest."""
    raw = _numeric(raw).loc[raw.index >= START]   # compare only the common 10-year window
    idx = list(NAMES)
    counts = raw[idx].notna().sum()
    short = counts[counts < MIN_DAYS]
    if len(short):
        raise ValueError(f"Short series (< {MIN_DAYS} days): {short.to_dict()}")
    firsts = raw[idx].apply(lambda s: s.first_valid_index())
    gap = (firsts.max() - firsts.min()).days
    if gap > MAX_START_GAP_DAYS:
        raise ValueError(f"Series start dates differ by {gap} days")


def save_snapshot(raw):
    """Run by hand from a notebook, never from the app, after a validated live fetch."""
    raw = _numeric(raw)
    check_coverage(raw)
    SNAPSHOT.parent.mkdir(exist_ok=True)
    raw.to_csv(SNAPSHOT)


def load_raw():
    """Live FRED first; validated snapshot only if live fails. Never writes to disk."""
    try:
        raw = fetch_fred()
        check_coverage(raw)
        return raw, "FRED (live)"
    except Exception:
        if not SNAPSHOT.exists():
            raise
        raw = pd.read_csv(SNAPSHOT, index_col=0, parse_dates=True, na_values=".")
        raw = _numeric(raw)
        raw = raw.loc[raw.index >= START]          # trim the snapshot to the same window
        check_coverage(raw)
        return raw, f"FRED snapshot through {raw.index.max().date()}"

def clean(raw):
    """Keep days when all four indices have a close; forward-fill the yield (max 5 days)."""
    raw = _numeric(raw)
    prices = raw[list(NAMES)].dropna()
    y10 = raw["y10"].ffill(limit=5).reindex(prices.index)
    return prices.join(y10)


def ret_vol_ratio(r):
    """Annualized mean daily return / annualized volatility (Sharpe with rf = 0)."""
    return (r.mean() * TD) / (r.std() * np.sqrt(TD))


def window_metrics(w, cols):
    rows = []
    for c in cols:
        p = w[c].dropna()
        r = p.pct_change().dropna()
        rows.append({"Index": NAMES[c],
                     "Total return": p.iloc[-1] / p.iloc[0] - 1,
                     "Ann. return": r.mean() * TD,
                     "Ann. volatility": r.std() * np.sqrt(TD),
                     "Return/Vol": ret_vol_ratio(r),
                     "Max drawdown": (p / p.cummax() - 1).min()})
    return pd.DataFrame(rows)


def yearly_metrics(w, cols):
    rows = []
    for c in cols:
        r = w[c].pct_change().dropna()
        for y, ry in r.groupby(r.index.year):
            rows.append({"Year": y, "Index": NAMES[c], "Days": len(ry),
                         "Return": (1 + ry).prod() - 1,
                         "Return/Vol": ret_vol_ratio(ry)})
    yt = pd.DataFrame(rows)
    yt["Partial"] = yt["Days"] < PARTIAL_DAYS
    yt["Year"] = yt["Year"].astype(str) + np.where(yt["Partial"], "*", "")
    yt["Ratio rank"] = yt.groupby("Year")["Return/Vol"].rank(ascending=False, method="min")
    return yt


def winners(yt):
    out = []
    for y, g in yt.groupby("Year", sort=True):
        s = g.sort_values("Return/Vol", ascending=False)
        out.append({"Year": y,
                    "Best Return/Vol": s.iloc[0]["Index"],
                    "Margin over 2nd": s.iloc[0]["Return/Vol"] - s.iloc[1]["Return/Vol"],
                    "Best return": g.loc[g["Return"].idxmax(), "Index"]})
    t = pd.DataFrame(out)
    t["Same winner?"] = t["Best Return/Vol"] == t["Best return"]
    return t