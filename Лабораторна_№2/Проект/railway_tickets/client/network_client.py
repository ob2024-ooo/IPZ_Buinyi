"""TCP-клієнт: надсилає JSON-запит на сервер і читає JSON-відповідь."""
import json
import socket


class ApiError(Exception):
    """Помилка, яку бачить користувач (від сервера або мережева)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class NetworkClient:
    def __init__(self, host="127.0.0.1", port=5055, timeout=5.0):
        self._host = host
        self._port = port
        self._timeout = timeout

    # --- властивості з get/set ---
    @property
    def host(self):
        return self._host

    @host.setter
    def host(self, value):
        if not value:
            raise ValueError("Адреса сервера не може бути порожньою")
        self._host = value

    @property
    def port(self):
        return self._port

    @port.setter
    def port(self, value):
        value = int(value)
        if not 1 <= value <= 65535:
            raise ValueError("Порт має бути в межах 1..65535")
        self._port = value

    def send(self, command, **fields):
        """Повертає (message, data) або кидає ApiError."""
        request = dict(fields, command=command)
        payload = (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            with socket.create_connection((self._host, self._port), timeout=self._timeout) as sock:
                sock.sendall(payload)
                reader = sock.makefile("rb")
                line = reader.readline()
        except socket.timeout:
            raise ApiError("TIMEOUT", "Сервер не відповів за %d с. Спробуйте пізніше." % self._timeout)
        except (ConnectionRefusedError, OSError):
            raise ApiError("NO_CONNECTION", "Не вдалося підключитися до сервера %s:%s. "
                                            "Запустіть серверну частину." % (self._host, self._port))
        if not line:
            raise ApiError("NO_RESPONSE", "Сервер закрив з'єднання без відповіді.")
        try:
            response = json.loads(line.decode("utf-8"))
        except ValueError:
            raise ApiError("BAD_RESPONSE", "Сервер надіслав некоректну відповідь.")
        if not response.get("success"):
            raise ApiError(response.get("code", "ERROR"), response.get("message", "Невідома помилка."))
        return response.get("message", ""), response.get("data", {})
