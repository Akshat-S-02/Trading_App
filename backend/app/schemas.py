from pydantic import BaseModel, Field

class LimitUpdate(BaseModel):
    # Percent of capital you may lose per day / month (RiskGate reads them as %).
    max_daily_dd: float = Field(gt=0, le=100, allow_inf_nan=False)
    max_monthly_dd: float = Field(gt=0, le=100, allow_inf_nan=False)
