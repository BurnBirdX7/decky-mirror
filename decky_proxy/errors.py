class ProxyError(Exception):
    status_code = 502


class InvalidResourceError(ProxyError):
    status_code = 400


class BlockedDestinationError(ProxyError):
    status_code = 403


class InvalidResourceSignatureError(ProxyError):
    status_code = 403


class InvalidCatalogueError(ProxyError):
    pass


class UpstreamRequestError(ProxyError):
    pass


class RedirectLimitError(ProxyError):
    pass


class UpstreamTimeoutError(ProxyError):
    status_code = 504
