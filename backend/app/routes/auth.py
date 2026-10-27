from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.controllers.auth_controller import AuthController
from app.database.session import get_db
from app.schemas.auth import LoginRequest, LoginResponse, UserRead
from app.utils.auth_exceptions import (
    AuthenticationUnavailableError,
    AuthorizationDeniedError,
    InvalidCredentialsError,
    LoginRateLimitedError,
)
from app.utils.security import bearer_scheme, get_token_claims, get_token_subject

router = APIRouter(prefix="/auth", tags=["auth"])
controller = AuthController()


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    try:
        token, user = controller.login(db, payload.username, payload.password)
        return {"access_token": token, "user": user}
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.") from exc
    except AuthenticationUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication service is unavailable.") from exc
    except AuthorizationDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to use this application.") from exc
    except LoginRateLimitedError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts. Try again later.") from exc


@router.get("/me", response_model=UserRead)
def me(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    user = controller.me(db, get_token_subject(credentials))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return user


@router.get("/menus")
def menus(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
    claims = get_token_claims(credentials)
    from app.config.menu_config import get_ldap_menu_config, get_mock_menu_config
    from app.config.settings import get_settings

    groups = claims.get("groups", [])
    menu_config = get_mock_menu_config() if get_settings().auth_mode == "mock" else get_ldap_menu_config()
    allowed_menus = menu_config.menus_for_groups(groups)
    return {
        # Re-evaluate against the active policy so a token issued under an old
        # menu configuration cannot keep showing removed or unauthorized items.
        "menus": allowed_menus,
        "menu_items": menu_config.items_for_groups(groups),
        "groups": groups,
    }
