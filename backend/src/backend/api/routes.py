from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Baboon Technologies API"}


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
