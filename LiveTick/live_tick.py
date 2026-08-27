from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Callable

# Import secure config for credential management
try:
    from Config.secure_config import get_credential, set_credential
    SECURE_CONFIG_AVAILABLE = True
except ImportError:
    try:
        from secure_config import get_credential, set_credential
        SECURE_CONFIG_AVAILABLE = True
    except ImportError:
        SECURE_CONFIG_AVAILABLE = False


DEFAULT_DATA_TYPE = "SymbolUpdate"
VALID_DATA_TYPES = {"SymbolUpdate", "DepthUpdate"}
FYERS_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = FYERS_DIR / "Config" / "LoginConfig" / "config.properties"


TickCallback = Callable[[Any], None]


@dataclass(frozen=True)
class Subscription:
    symbol: str
    data_type: str = DEFAULT_DATA_TYPE


def normalize_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if not value:
        raise ValueError("symbol cannot be empty")
    if ":" in value:
        return value
    return f"NSE:{value}-EQ"


def read_config_property(key: str, config_path: str | Path = DEFAULT_CONFIG_PATH) -> str | None:
    """
    Read config property with secure credential lookup.

    Priority: Windows Credential Manager > env var > file
    """
    # Try secure config first for sensitive keys
    sensitive_keys = {'appId', 'secretID', 'auth_code', 'access_token', 'REDIRECT'}
    if SECURE_CONFIG_AVAILABLE and key in sensitive_keys:
        value = get_credential(key)
        if value:
            return value

    # Fallback to file
    path = Path(config_path)
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            candidate_key, value = stripped.split("=", 1)
            if candidate_key.strip() == key:
                return value.strip()
    return None


def write_config_property(key: str, value: str, config_path: str | Path = DEFAULT_CONFIG_PATH) -> bool:
    """
    Write config property to secure storage (keyring) for sensitive keys,
    or to file for non-sensitive keys.
    """
    sensitive_keys = {'appId', 'secretID', 'auth_code', 'access_token', 'REDIRECT'}
    if SECURE_CONFIG_AVAILABLE and key in sensitive_keys:
        return set_credential(key, value)

    # Fallback to file
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    key_found = False

    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip().startswith(f"{key}="):
                    lines.append(f"{key}={value}\n")
                    key_found = True
                else:
                    lines.append(line)

    if not key_found:
        lines.append(f"{key}={value}\n")

    with path.open("w", encoding="utf-8") as handle:
        handle.writelines(lines)
    return True


def websocket_access_token(config_path: str | Path = DEFAULT_CONFIG_PATH) -> str:
    app_id = read_config_property("appId", config_path)
    access_token = read_config_property("access_token", config_path)
    if not app_id or not access_token:
        raise RuntimeError(
            f"Missing appId or access_token. "
            f"Run: py -m Config.secure_config setup"
        )
    if access_token.startswith(f"{app_id}:"):
        return access_token
    return f"{app_id}:{access_token}"


def default_tick_printer(message: Any) -> None:
    print("Live tick:", message)


class LiveTickClient:
    """
    Small production wrapper around FYERS DataSocket.

    FYERS exposes subscribe/unsubscribe methods but the v3 docs do not show a
    supported API to list current subscriptions. This class keeps our local
    registry so duplicate subscribe calls are avoided and reconnects can
    re-subscribe cleanly.
    """

    def __init__(
        self,
        *,
        data_type: str = DEFAULT_DATA_TYPE,
        litemode: bool = False,
        write_to_file: bool = False,
        log_path: str = "",
        reconnect: bool = True,
        access_token: str | None = None,
        config_path: str | Path = DEFAULT_CONFIG_PATH,
        on_tick: TickCallback | None = None,
    ) -> None:
        self.data_type = self._validate_data_type(data_type)
        self.litemode = litemode
        self.write_to_file = write_to_file
        self.log_path = log_path
        self.reconnect = reconnect
        self.access_token = access_token
        self.config_path = Path(config_path)
        self.on_tick = on_tick or default_tick_printer
        self._socket = None
        self._connected = False
        self._subscriptions: set[Subscription] = set()
        self._lock = RLock()

    @staticmethod
    def _validate_data_type(data_type: str) -> str:
        normalized = data_type.strip()
        for valid_data_type in VALID_DATA_TYPES:
            if normalized.lower() == valid_data_type.lower():
                return valid_data_type
        if normalized not in VALID_DATA_TYPES:
            raise ValueError(f"Unsupported data_type {data_type!r}. Use one of {sorted(VALID_DATA_TYPES)}")
        return normalized

    def subscriptions(self) -> tuple[Subscription, ...]:
        with self._lock:
            return tuple(sorted(self._subscriptions, key=lambda item: (item.data_type, item.symbol)))

    def _socket_access_token(self) -> str:
        if self.access_token:
            return self.access_token
        return websocket_access_token(self.config_path)

    def is_subscribed(self, symbol: str, data_type: str | None = None) -> bool:
        subscription = Subscription(
            normalize_symbol(symbol),
            self._validate_data_type(data_type or self.data_type),
        )
        with self._lock:
            return subscription in self._subscriptions

    def subscribe(self, symbol: str, data_type: str | None = None) -> bool:
        subscription = Subscription(
            normalize_symbol(symbol),
            self._validate_data_type(data_type or self.data_type),
        )
        with self._lock:
            if subscription in self._subscriptions:
                print(f"{subscription.symbol} is already subscribed for {subscription.data_type}.")
                return False

            self._subscriptions.add(subscription)
            if self._connected and self._socket is not None:
                try:
                    self._socket.subscribe(
                        symbols=[subscription.symbol],
                        data_type=subscription.data_type,
                    )
                except Exception:
                    self._subscriptions.remove(subscription)
                    raise
                print(f"Subscribed to {subscription.symbol} ({subscription.data_type}).")
            else:
                print(f"Queued subscription for {subscription.symbol} ({subscription.data_type}).")
            return True

    def unsubscribe(self, symbol: str, data_type: str | None = None) -> bool:
        subscription = Subscription(
            normalize_symbol(symbol),
            self._validate_data_type(data_type or self.data_type),
        )
        with self._lock:
            if subscription not in self._subscriptions:
                print(f"{subscription.symbol} is not subscribed for {subscription.data_type}.")
                return False

            if self._connected and self._socket is not None:
                self._socket.unsubscribe(
                    symbols=[subscription.symbol],
                    data_type=subscription.data_type,
                )
                print(f"Unsubscribed from {subscription.symbol} ({subscription.data_type}).")
            self._subscriptions.remove(subscription)
            return True

    def run(self, symbol: str | None = None, data_type: str | None = None):
        if symbol:
            self.subscribe(symbol, data_type)
        return self.connect()

    def connect(self):
        if self._socket is not None:
            return self._socket

        try:
            from fyers_apiv3.FyersWebsocket import data_ws
        except ImportError as exc:
            raise RuntimeError("Install fyers-apiv3 before using LiveTick websocket streaming.") from exc

        def on_message(message):
            self.on_tick(message)

        def on_error(message):
            print("Live websocket error:", message)

        def on_close(message):
            with self._lock:
                self._connected = False
            print("Live websocket closed:", message)

        def on_connect():
            with self._lock:
                self._connected = True
                subscriptions = sorted(
                    self._subscriptions,
                    key=lambda item: (item.data_type, item.symbol),
                )

            print("Live websocket connected.")
            for subscription in subscriptions:
                try:
                    self._socket.subscribe(
                        symbols=[subscription.symbol],
                        data_type=subscription.data_type,
                    )
                    print(f"Subscribed to {subscription.symbol} ({subscription.data_type}).")
                except Exception as exc:
                    print(f"Failed to subscribe {subscription.symbol} ({subscription.data_type}): {exc}")
            self._socket.keep_running()

        self._socket = data_ws.FyersDataSocket(
            access_token=self._socket_access_token(),
            log_path=self.log_path,
            litemode=self.litemode,
            write_to_file=self.write_to_file,
            reconnect=self.reconnect,
            on_connect=on_connect,
            on_close=on_close,
            on_error=on_error,
            on_message=on_message,
        )
        self._socket.connect()
        return self._socket

    def close(self) -> None:
        with self._lock:
            socket = self._socket
            self._connected = False
            self._socket = None

        if socket is None:
            return

        # Closing the socket drops server-side subscriptions. Calling unsubscribe
        # during teardown can produce FYERS "invalid symbol" noise if the SDK has
        # already cleared its internal subscription registry.
        for method_name in ("close_connection", "close", "disconnect"):
            method = getattr(socket, method_name, None)
            if callable(method):
                try:
                    method()
                    break
                except Exception:
                    continue


_default_client: LiveTickClient | None = None


def get_default_client(**kwargs) -> LiveTickClient:
    global _default_client
    if _default_client is None:
        _default_client = LiveTickClient(**kwargs)
    return _default_client


def subscribe(symbol: str, data_type: str = DEFAULT_DATA_TYPE) -> bool:
    return get_default_client(data_type=data_type).subscribe(symbol, data_type)


def unsubscribe(symbol: str, data_type: str = DEFAULT_DATA_TYPE) -> bool:
    return get_default_client(data_type=data_type).unsubscribe(symbol, data_type)


def is_subscribed(symbol: str, data_type: str = DEFAULT_DATA_TYPE) -> bool:
    return get_default_client(data_type=data_type).is_subscribed(symbol, data_type)


def LiveTick(
    symbol: str,
    *,
    data_type: str = DEFAULT_DATA_TYPE,
    litemode: bool = False,
    write_to_file: bool = False,
    log_path: str = "",
    access_token: str | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    on_tick: TickCallback | None = None,
):
    client = get_default_client(
        data_type=data_type,
        litemode=litemode,
        write_to_file=write_to_file,
        log_path=log_path,
        access_token=access_token,
        config_path=config_path,
        on_tick=on_tick,
    )
    normalized = normalize_symbol(symbol)
    if client.is_subscribed(normalized, data_type):
        print(f"{normalized} is already subscribed. Starting tick stream.")
    else:
        client.subscribe(normalized, data_type)
    return client.connect()
