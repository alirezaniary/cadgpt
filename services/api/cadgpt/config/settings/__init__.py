"""Settings are split by environment and never branch on a DEBUG flag.

`base` holds what is true everywhere. `local`, `test` and `production` each state their own
posture explicitly, so reading one file tells you how that environment actually behaves --
rather than tracing conditionals through a single settings module.
"""
