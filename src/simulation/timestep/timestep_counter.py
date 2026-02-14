from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd


INTERVALS = {
    "hourly":    {"hours": 1},
    "weekly":    {"days": 7},
    "monthly":   {"months": 1},
    "quarterly": {"months": 3},
}


LABEL_FMT = {
    "hourly":    lambda d, t: f"Hour {t}  ({d.strftime('%b %d, %Y %I:%M %p')})",
    "weekly":    lambda d, t: f"Week {t}  ({d.strftime('%b %d, %Y')})",
    "monthly":   lambda d, t: d.strftime("%B %Y"),
    "quarterly": lambda d, t: f"Q{((d.month - 1) // 3) + 1} {d.year}",
}


class TimeStepCounter:

    def __init__(self, start_date: datetime, interval: str = "weekly"):
        if interval not in INTERVALS:
            raise ValueError(f"Invalid interval '{interval}'. Choose from: {list(INTERVALS.keys())}")

        self.t = 1
        self.current_date = start_date
        self.start_date = start_date
        self.interval = interval
        self._delta = relativedelta(**INTERVALS[interval])


    def step(self):
        self.t += 1
        self.current_date += self._delta
        return self.t, self.current_date


    def reset(self):
        self.t = 1
        self.current_date = self.start_date


    def __repr__(self):
        return (
            f"TimeStepCounter("
            f"t={self.t}, "
            f"date={self.current_date}, "
            f"interval={self.interval})"
        )


def generate_timestep_table(
    start_date: datetime,
    n_steps: int,
    interval: str = "weekly",
) -> pd.DataFrame:
 
    counter = TimeStepCounter(start_date=start_date, interval=interval)
    label_fn = LABEL_FMT[interval]
    delta = relativedelta(**INTERVALS[interval])
    rows = []

    current = start_date

    for step in range(1, n_steps + 1):
        date_start = current
        if interval == "hourly":
            date_end = current + delta - relativedelta(seconds=1)
        else:
            date_end = current + delta - relativedelta(days=1)
        rows.append({
            "t":            step,
            "date_start":   date_start,
            "date_end":     date_end,
            "period_label": label_fn(date_start, step),
        })
        current += delta

    return pd.DataFrame(rows)
