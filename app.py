"""Application wiring — shared by main, executor, telegram."""

from dataclasses import dataclass

from account.account import AccountPaths
from broker.rate_limiter import RateLimiter
from broker.toss_auth import TossAuth
from broker.toss_client import TossClient
from config.settings import Settings, get_settings
from cycles.cycle_tracker import CycleTracker
from state.runtime_settings import RuntimeSettings
from state.state import StateStore
from strategy.fill_processor import FillProcessor
from strategy.fill_reconciler import FillReconciler
from strategy.strategy_v40 import InfiniteStrategyV40


@dataclass
class App:
    settings: Settings
    paths: AccountPaths
    state: StateStore
    runtime: RuntimeSettings
    cycles: CycleTracker
    strategy: InfiniteStrategyV40
    fills: FillProcessor
    limiter: RateLimiter
    broker: TossClient
    reconciler: FillReconciler | None = None

    @classmethod
    def create(cls) -> "App":
        settings = get_settings()
        paths = AccountPaths()
        limiter = RateLimiter()
        dry = settings.dry_run or not settings.has_toss
        auth = TossAuth(
            settings.toss_client_id,
            settings.toss_client_secret,
            paths.token_cache,
            limiter,
        )
        broker = TossClient(auth, settings.toss_account_seq, limiter, dry_run=dry)
        app = cls(
            settings=settings,
            paths=paths,
            state=StateStore(paths),
            runtime=RuntimeSettings(),
            cycles=CycleTracker(str(paths.root)),
            strategy=InfiniteStrategyV40(),
            fills=FillProcessor(),
            limiter=limiter,
            broker=broker,
        )
        app.reconciler = FillReconciler(app)
        return app
