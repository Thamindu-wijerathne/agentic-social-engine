import logging

from fastapi import APIRouter

from app.agents.trend_agent import TrendAgent

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/test")
def test():
    logger.info("/test handler start")
    trend_agent = TrendAgent()
    response = trend_agent.run_agent(
        "Give me top trending US politics and public-affairs news for older adults. "
        "Prioritize government policy, economy, healthcare, Social Security, retirement, and safety."
    )
    logger.info("/test handler done response_type=%s", type(response).__name__)
    return response
