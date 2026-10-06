class MirrorError(Exception):
    status_code = 502


class InvalidResourceError(MirrorError):
    status_code = 400


class BlockedDestinationError(MirrorError):
    status_code = 403


class InvalidCatalogueError(MirrorError):
    pass


class UpstreamRequestError(MirrorError):
    pass


class RedirectLimitError(MirrorError):
    pass


class UpstreamTimeoutError(MirrorError):
    status_code = 504
