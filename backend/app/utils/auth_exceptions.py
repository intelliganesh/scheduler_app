class InvalidCredentialsError(Exception):
    pass


class AuthenticationUnavailableError(Exception):
    pass


class LoginRateLimitedError(Exception):
    pass


class AuthorizationDeniedError(Exception):
    pass
