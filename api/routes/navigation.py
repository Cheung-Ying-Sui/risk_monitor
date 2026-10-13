from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from api.schemas.navigation import NavigationPredictionResponse
from risk_monitor.navigation.prediction_service import (
    NavigationPredictionDataError,
    NavigationPredictionNotFoundError,
    VesselNavigationPredictionService,
)


router = APIRouter(prefix="/api/v1/vessels", tags=["navigation"])
insurance_prediction_router = APIRouter(prefix="/api/v1/insurance/voyage-predictions", tags=["navigation"])


def get_insurance_prediction_service():
    from risk_monitor.navigation.insurance_prediction_service import InsuranceVoyagePredictionService
    return InsuranceVoyagePredictionService()


def refresh_insurance_predictions(service):
    import logging
    try:
        service.list_predictions(refresh=True)
    except Exception as exc:
        logging.getLogger(__name__).warning('insurance_prediction_refresh_failed type=%s', type(exc).__name__)


@insurance_prediction_router.get('')
def list_insurance_predictions(background_tasks: BackgroundTasks, service=Depends(get_insurance_prediction_service)):
    try:
        items = service.list_predictions()
    except Exception as exc:
        raise HTTPException(503, '承保航程预测暂不可用，请稍后重试。') from exc
    if any(item['status'] == 'route_pending' for item in items):
        background_tasks.add_task(refresh_insurance_predictions, service)
    return {'items': items}


def get_navigation_prediction_service() -> VesselNavigationPredictionService:
    return VesselNavigationPredictionService()


@router.get(
    "/{vessel_id}/navigation-prediction",
    response_model=NavigationPredictionResponse,
)
def get_navigation_prediction(
    vessel_id: str,
    service: VesselNavigationPredictionService = Depends(
        get_navigation_prediction_service
    ),
) -> NavigationPredictionResponse:
    try:
        prediction = service.get_prediction(vessel_id)
    except NavigationPredictionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NavigationPredictionDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Navigation prediction failed.",
        ) from exc
    return NavigationPredictionResponse.model_validate(prediction)
