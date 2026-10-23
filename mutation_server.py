"""
mutation_server.py  —  Stickercast Phase 2
FastAPI server exposing Google Ads mutation operations as MCP-compatible tools.

Start:
    set MUTATION_API_KEY=your-secret-key-here
    set GOOGLE_ADS_YAML=/path/to/google-ads.yaml
    python -m uvicorn mutation_server:app --reload --port 8001

All endpoints accept JSON and return structured results.
Protected endpoints require X-API-Key header matching MUTATION_API_KEY env var.
"""

import os
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GOOGLE_ADS_YAML = os.environ.get("GOOGLE_ADS_YAML", "google-ads.yaml")
MUTATION_API_KEY = os.environ.get("MUTATION_API_KEY", "dev-key-change-me")

app = FastAPI(
    title="Stickercast Google Ads Mutation Server",
    description="Phase 2 MCP-compatible write API for Google Ads",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def require_api_key(x_api_key: str = Header(...)):
    if x_api_key != MUTATION_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")


# ---------------------------------------------------------------------------
# Shared client helper
# ---------------------------------------------------------------------------

def get_client() -> GoogleAdsClient:
    try:
        return GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load Google Ads client: {e}")


def handle_gads_exception(ex: GoogleAdsException):
    errors = [
        {"code": str(e.error_code), "message": e.message}
        for e in ex.failure.errors
    ]
    raise HTTPException(status_code=400, detail={"google_ads_errors": errors})


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CreateBudgetRequest(BaseModel):
    customer_id: str
    name: Optional[str] = None
    daily_budget_micros: int = Field(..., description="Daily budget in micros (1000000 = $1.00)")
    delivery_method: str = Field("STANDARD", description="STANDARD or ACCELERATED")


class CreateCampaignRequest(BaseModel):
    customer_id: str
    name: str
    budget_resource_name: str
    status: str = Field("PAUSED", description="ENABLED or PAUSED")
    channel_type: str = Field("SEARCH", description="SEARCH, DISPLAY, SHOPPING, etc.")
    target_google_search: bool = True
    target_search_network: bool = False
    target_content_network: bool = False


class UpdateCampaignStatusRequest(BaseModel):
    customer_id: str
    campaign_id: str
    status: str = Field(..., description="ENABLED, PAUSED, or REMOVED")


class UpdateCampaignBudgetRequest(BaseModel):
    customer_id: str
    campaign_budget_resource_name: str
    daily_budget_micros: int


class CreateAdGroupRequest(BaseModel):
    customer_id: str
    campaign_resource_name: str
    name: str
    status: str = Field("PAUSED", description="ENABLED or PAUSED")
    cpc_bid_micros: int = Field(1_000_000, description="Max CPC in micros")


class CreateKeywordRequest(BaseModel):
    customer_id: str
    ad_group_resource_name: str
    keyword_text: str
    match_type: str = Field("BROAD", description="BROAD, PHRASE, or EXACT")
    cpc_bid_micros: Optional[int] = None
    status: str = Field("ENABLED", description="ENABLED or PAUSED")


class UpdateAdGroupStatusRequest(BaseModel):
    customer_id: str
    ad_group_id: str
    status: str


class MutateKeywordStatusRequest(BaseModel):
    customer_id: str
    ad_group_criterion_resource_name: str
    status: str = Field(..., description="ENABLED or PAUSED")


class UpdateAdStatusRequest(BaseModel):
    customer_id: str
    ad_group_id: str
    ad_id: str = Field(..., description="Numeric ad ID (not the full resource name)")
    status: str = Field(..., description="ENABLED, PAUSED, or REMOVED")


class UpdateAdFinalUrlRequest(BaseModel):
    customer_id: str
    ad_group_id: str
    ad_id: str = Field(..., description="Numeric ad ID")
    final_url: str = Field(..., description="New final URL (e.g., https://example.com/page)")


class UpdateSitelinkAssetFinalUrlRequest(BaseModel):
    customer_id: str
    asset_resource_name: str = Field(..., description="Full resource name of the sitelink asset (e.g., customers/123/assets/456)")
    final_url: str = Field(..., description="New final URL (e.g., https://example.com/contact)")


class UpdateCallAssetScheduleRequest(BaseModel):
    customer_id: str
    call_asset_resource_name: str = Field(..., description="Full resource name of the call asset (e.g., customers/123/assets/456)")
    schedules: list[ScheduleSlot] = Field(..., description="List of time slots when the call asset should be visible")


class UpdateKeywordBidRequest(BaseModel):
    customer_id: str
    ad_group_criterion_resource_name: str
    cpc_bid_micros: int = Field(..., description="New CPC bid in micros. 1000000 = $1.00")


class AddNegativeKeywordRequest(BaseModel):
    customer_id: str
    campaign_id: str
    keyword_text: str
    match_type: str = Field("BROAD", description="BROAD, PHRASE, or EXACT")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "server": "stickercast-mutation-v0.3"}


# ---------------------------------------------------------------------------
# Tool manifest
# ---------------------------------------------------------------------------

@app.get("/tools")
def list_tools():
    return {
        "tools": [
            {"name": "create_campaign_budget", "endpoint": "POST /budgets/create"},
            {"name": "create_campaign", "endpoint": "POST /campaigns/create"},
            {"name": "update_campaign_status", "endpoint": "POST /campaigns/update-status"},
            {"name": "update_campaign_budget", "endpoint": "POST /budgets/update"},
            {"name": "create_ad_group", "endpoint": "POST /ad-groups/create"},
            {"name": "update_ad_group_status", "endpoint": "POST /ad-groups/update-status"},
            {"name": "create_keyword", "endpoint": "POST /keywords/create"},
            {"name": "update_keyword_status", "endpoint": "POST /keywords/update-status"},
            {"name": "update_keyword_bid", "endpoint": "POST /keywords/update-bid"},
            {"name": "add_negative_keyword", "endpoint": "POST /keywords/add-negative"},
            {"name": "remove_campaign_asset", "endpoint": "POST /assets/remove-campaign-asset"},
            {"name": "remove_campaign_image_asset", "endpoint": "POST /assets/remove-campaign-image-asset"},
            {"name": "update_geo_target_type", "endpoint": "POST /campaigns/update-geo-target-type"},
            {"name": "update_ad_schedule", "endpoint": "POST /campaigns/update-ad-schedule"},
            {"name": "update_conversion_action_call_duration", "endpoint": "POST /conversions/update-call-duration"},
            {"name": "create_phone_call_conversion", "endpoint": "POST /conversions/create-phone-call-conversion"},
            {"name": "create_form_submission_conversion", "endpoint": "POST /conversions/create-form-submission-conversion"},
            {"name": "add_location_criterion", "endpoint": "POST /locations/add-location-criterion"},
            {"name": "remove_location_criterion", "endpoint": "POST /locations/remove-location-criterion"},
            {"name": "add_proximity_radius", "endpoint": "POST /locations/add-proximity-radius"},
            {"name": "create_ad_schedule", "endpoint": "POST /campaigns/create-ad-schedule"},
            {"name": "delete_ad_schedule", "endpoint": "POST /campaigns/delete-ad-schedule"},
            {"name": "update_ad_status", "endpoint": "POST /ads/update-status"},
            {"name": "update_ad_final_url", "endpoint": "POST /ads/update-final-url"},
            {"name": "update_call_asset_schedule", "endpoint": "POST /assets/update-call-asset-schedule"},
            {"name": "update_sitelink_final_url", "endpoint": "POST /assets/update-sitelink-final-url"},
            {"name": "update_demographic_bid_modifier", "endpoint": "POST /ad-groups/update-demographic-bid-modifier"},
            {"name": "create_demographic_criterion", "endpoint": "POST /ad-groups/create-demographic-criterion"},
        ]
    }


# ---------------------------------------------------------------------------
# Budget endpoints
# ---------------------------------------------------------------------------

@app.post("/budgets/create", dependencies=[Depends(require_api_key)])
def create_campaign_budget(req: CreateBudgetRequest):
    client = get_client()
    service = client.get_service("CampaignBudgetService")
    op = client.get_type("CampaignBudgetOperation")
    budget = op.create

    budget.name = req.name or f"Budget-{uuid.uuid4().hex[:8]}"
    budget.amount_micros = req.daily_budget_micros
    budget.delivery_method = getattr(
        client.enums.BudgetDeliveryMethodEnum, req.delivery_method
    )

    try:
        resp = service.mutate_campaign_budgets(customer_id=req.customer_id, operations=[op])
        rn = resp.results[0].resource_name
        return {"resource_name": rn, "name": budget.name, "daily_budget_micros": req.daily_budget_micros}
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


@app.post("/budgets/update", dependencies=[Depends(require_api_key)])
def update_campaign_budget(req: UpdateCampaignBudgetRequest):
    client = get_client()
    service = client.get_service("CampaignBudgetService")
    op = client.get_type("CampaignBudgetOperation")
    budget = op.update

    budget.resource_name = req.campaign_budget_resource_name
    budget.amount_micros = req.daily_budget_micros
    op.update_mask.paths.append("amount_micros")

    try:
        resp = service.mutate_campaign_budgets(customer_id=req.customer_id, operations=[op])
        return {"resource_name": resp.results[0].resource_name, "new_daily_budget_micros": req.daily_budget_micros}
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


# ---------------------------------------------------------------------------
# Campaign endpoints
# ---------------------------------------------------------------------------

@app.post("/campaigns/create", dependencies=[Depends(require_api_key)])
def create_campaign(req: CreateCampaignRequest):
    client = get_client()
    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    campaign = op.create

    campaign.name = req.name
    campaign.status = getattr(client.enums.CampaignStatusEnum, req.status)
    campaign.advertising_channel_type = getattr(
        client.enums.AdvertisingChannelTypeEnum, req.channel_type
    )
    campaign.campaign_budget = req.budget_resource_name

    # Required field for Google Ads API v24
    campaign.contains_eu_political_advertising = (
        client.enums.EuPoliticalAdvertisingStatusEnum
        .DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    )

    campaign.manual_cpc.enhanced_cpc_enabled = False
    campaign.network_settings.target_google_search = req.target_google_search
    campaign.network_settings.target_search_network = req.target_search_network
    campaign.network_settings.target_content_network = req.target_content_network

    try:
        resp = service.mutate_campaigns(customer_id=req.customer_id, operations=[op])
        rn = resp.results[0].resource_name
        return {"resource_name": rn, "name": req.name, "status": req.status}
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


@app.post("/campaigns/update-status", dependencies=[Depends(require_api_key)])
def update_campaign_status(req: UpdateCampaignStatusRequest):
    client = get_client()
    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    campaign = op.update

    campaign.resource_name = service.campaign_path(req.customer_id, req.campaign_id)
    campaign.status = getattr(client.enums.CampaignStatusEnum, req.status)
    op.update_mask.paths.append("status")

    try:
        resp = service.mutate_campaigns(customer_id=req.customer_id, operations=[op])
        return {"resource_name": resp.results[0].resource_name, "new_status": req.status}
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


# ---------------------------------------------------------------------------
# Ad Group endpoints
# ---------------------------------------------------------------------------

@app.post("/ad-groups/create", dependencies=[Depends(require_api_key)])
def create_ad_group(req: CreateAdGroupRequest):
    client = get_client()
    service = client.get_service("AdGroupService")
    op = client.get_type("AdGroupOperation")
    ad_group = op.create

    ad_group.name = req.name
    ad_group.campaign = req.campaign_resource_name
    ad_group.status = getattr(client.enums.AdGroupStatusEnum, req.status)
    ad_group.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
    ad_group.cpc_bid_micros = req.cpc_bid_micros

    try:
        resp = service.mutate_ad_groups(customer_id=req.customer_id, operations=[op])
        rn = resp.results[0].resource_name
        return {"resource_name": rn, "name": req.name, "status": req.status}
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


@app.post("/ad-groups/update-status", dependencies=[Depends(require_api_key)])
def update_ad_group_status(req: UpdateAdGroupStatusRequest):
    client = get_client()
    service = client.get_service("AdGroupService")
    op = client.get_type("AdGroupOperation")
    ad_group = op.update

    ad_group.resource_name = service.ad_group_path(req.customer_id, req.ad_group_id)
    ad_group.status = getattr(client.enums.AdGroupStatusEnum, req.status)
    op.update_mask.paths.append("status")

    try:
        resp = service.mutate_ad_groups(customer_id=req.customer_id, operations=[op])
        return {"resource_name": resp.results[0].resource_name, "new_status": req.status}
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


# ---------------------------------------------------------------------------
# Keyword endpoints
# ---------------------------------------------------------------------------

@app.post("/keywords/create", dependencies=[Depends(require_api_key)])
def create_keyword(req: CreateKeywordRequest):
    """
    Two-pass exemption pattern (exception-based, matches fix1d_patch_with_exemptions.py):
    Pass 1 — attempt normally, catch GoogleAdsException.
    If all errors are exemptible policy violations, collect keys and retry.
    Pass 2 — resubmit with exempt_policy_violation_keys attached.
    Non-exemptible violations raise 400 immediately.
    """
    client = get_client()
    service = client.get_service("AdGroupCriterionService")

    def _build_op(exempt_keys=None):
        op = client.get_type("AdGroupCriterionOperation")
        c = op.create
        c.ad_group = req.ad_group_resource_name
        c.status = getattr(client.enums.AdGroupCriterionStatusEnum, req.status)
        c.keyword.text = req.keyword_text
        c.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, req.match_type)
        if req.cpc_bid_micros:
            c.cpc_bid_micros = req.cpc_bid_micros
        if exempt_keys:
            for key in exempt_keys:
                ek = client.get_type("PolicyViolationKey")
                ek.policy_name = key["policy_name"]
                ek.violating_text = key["violating_text"]
                op.exempt_policy_violation_keys.append(ek)
        return op

    def _mutate(op):
        return service.mutate_ad_group_criteria(
            customer_id=req.customer_id, operations=[op]
        )

    # ── Pass 1 ────────────────────────────────────────────────────────────
    try:
        resp = _mutate(_build_op())
        return {
            "resource_name": resp.results[0].resource_name,
            "keyword": req.keyword_text,
            "match_type": req.match_type,
            "status": req.status,
            "exemptions_applied": [],
        }
    except GoogleAdsException as ex:
        exempt_keys = []
        for error in ex.failure.errors:
            pvd = error.details.policy_violation_details
            if pvd.key.policy_name and pvd.is_exemptible:
                exempt_keys.append({
                    "policy_name": pvd.key.policy_name,
                    "violating_text": pvd.key.violating_text,
                })
            else:
                # Non-policy error or non-exemptible — surface immediately
                handle_gads_exception(ex)
        if not exempt_keys:
            handle_gads_exception(ex)

    # ── Pass 2 — retry with exemption keys ────────────────────────────────
    try:
        resp = _mutate(_build_op(exempt_keys=exempt_keys))
        return {
            "resource_name": resp.results[0].resource_name,
            "keyword": req.keyword_text,
            "match_type": req.match_type,
            "status": req.status,
            "exemptions_applied": exempt_keys,
        }
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


@app.post("/keywords/update-status", dependencies=[Depends(require_api_key)])
def update_keyword_status(req: MutateKeywordStatusRequest):
    client = get_client()
    service = client.get_service("AdGroupCriterionService")
    op = client.get_type("AdGroupCriterionOperation")
    criterion = op.update

    criterion.resource_name = req.ad_group_criterion_resource_name
    criterion.status = getattr(client.enums.AdGroupCriterionStatusEnum, req.status)
    op.update_mask.paths.append("status")

    try:
        resp = service.mutate_ad_group_criteria(customer_id=req.customer_id, operations=[op])
        return {"resource_name": resp.results[0].resource_name, "new_status": req.status}
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


@app.post("/keywords/update-bid", dependencies=[Depends(require_api_key)])
def update_keyword_bid(req: UpdateKeywordBidRequest):
    """Update the CPC bid for a specific keyword."""
    client = get_client()
    service = client.get_service("AdGroupCriterionService")
    op = client.get_type("AdGroupCriterionOperation")
    criterion = op.update

    criterion.resource_name = req.ad_group_criterion_resource_name
    criterion.cpc_bid_micros = req.cpc_bid_micros
    op.update_mask.paths.append("cpc_bid_micros")

    try:
        resp = service.mutate_ad_group_criteria(customer_id=req.customer_id, operations=[op])
        return {
            "resource_name": resp.results[0].resource_name,
            "new_cpc_bid_micros": req.cpc_bid_micros,
            "new_cpc_bid_dollars": round(req.cpc_bid_micros / 1_000_000, 2),
        }
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


@app.post("/keywords/add-negative", dependencies=[Depends(require_api_key)])
def add_negative_keyword(req: AddNegativeKeywordRequest):
    """Add a negative keyword at the campaign level."""
    client = get_client()
    service = client.get_service("CampaignCriterionService")
    op = client.get_type("CampaignCriterionOperation")
    criterion = op.create

    campaign_service = client.get_service("CampaignService")
    criterion.campaign = campaign_service.campaign_path(req.customer_id, req.campaign_id)
    criterion.negative = True
    criterion.keyword.text = req.keyword_text
    criterion.keyword.match_type = getattr(
        client.enums.KeywordMatchTypeEnum, req.match_type
    )

    try:
        resp = service.mutate_campaign_criteria(customer_id=req.customer_id, operations=[op])
        rn = resp.results[0].resource_name
        return {
            "resource_name": rn,
            "negative_keyword": req.keyword_text,
            "match_type": req.match_type,
            "campaign_id": req.campaign_id,
        }
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


class RemoveNegativeKeywordRequest(BaseModel):
    customer_id: str
    campaign_criterion_resource_name: str


class UpdateCampaignCpcCeilingRequest(BaseModel):
    customer_id: str
    campaign_id: str
    cpc_ceiling_micros: int = Field(..., description="Max CPC ceiling in micros. 3000000 = $3.00")


@app.post("/keywords/remove-negative", dependencies=[Depends(require_api_key)])
def remove_negative_keyword(req: RemoveNegativeKeywordRequest):
    """Remove a campaign-level negative keyword by resource name."""
    client = get_client()
    service = client.get_service("CampaignCriterionService")
    op = client.get_type("CampaignCriterionOperation")
    op.remove = req.campaign_criterion_resource_name

    try:
        resp = service.mutate_campaign_criteria(customer_id=req.customer_id, operations=[op])
        return {"removed": req.campaign_criterion_resource_name, "status": "success"}
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


@app.post("/campaigns/update-cpc-ceiling", dependencies=[Depends(require_api_key)])
def update_campaign_cpc_ceiling(req: UpdateCampaignCpcCeilingRequest):
    """Update the maximize clicks CPC bid ceiling for a campaign."""
    client = get_client()
    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    campaign = op.update

    campaign.resource_name = service.campaign_path(req.customer_id, req.campaign_id)
    campaign.target_spend.cpc_bid_ceiling_micros = req.cpc_ceiling_micros
    op.update_mask.paths.append("target_spend.cpc_bid_ceiling_micros")

    try:
        resp = service.mutate_campaigns(customer_id=req.customer_id, operations=[op])
        return {
            "resource_name": resp.results[0].resource_name,
            "new_cpc_ceiling_micros": req.cpc_ceiling_micros,
            "new_cpc_ceiling_dollars": round(req.cpc_ceiling_micros / 1_000_000, 2),
        }
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


class RemoveAdRequest(BaseModel):
    customer_id: str
    ad_group_ad_resource_name: str


class CreateRsaRequest(BaseModel):
    customer_id: str
    ad_group_resource_name: str
    final_url: str
    headlines: list[str] = Field(..., description="List of headlines (max 15, each max 30 chars)")
    descriptions: list[str] = Field(..., description="List of descriptions (max 4, each max 90 chars)")
    status: str = Field("PAUSED", description="ENABLED or PAUSED")


@app.post("/ads/remove", dependencies=[Depends(require_api_key)])
def remove_ad(req: RemoveAdRequest):
    """Remove an ad from an ad group by its ad_group_ad resource name."""
    client = get_client()
    service = client.get_service("AdGroupAdService")
    op = client.get_type("AdGroupAdOperation")
    op.remove = req.ad_group_ad_resource_name

    try:
        resp = service.mutate_ad_group_ads(customer_id=req.customer_id, operations=[op])
        return {"removed": req.ad_group_ad_resource_name, "status": "success"}
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


@app.post("/ads/update-status", dependencies=[Depends(require_api_key)])
def update_ad_status(req: UpdateAdStatusRequest):
    """
    Update the status of an ad in an ad group.
    Status can be ENABLED, PAUSED, or REMOVED.
    """
    try:
        client = get_client()
        service = client.get_service("AdGroupAdService")
        
        # Construct the ad_group_ad resource name
        ad_group_ad_resource_name = f"customers/{req.customer_id}/adGroupAds/{req.ad_group_id}~{req.ad_id}"
        
        op = client.get_type("AdGroupAdOperation")
        ad_group_ad = op.update
        ad_group_ad.resource_name = ad_group_ad_resource_name
        ad_group_ad.status = getattr(client.enums.AdGroupAdStatusEnum, req.status)
        
        op.update_mask.paths.append("status")
        
        resp = service.mutate_ad_group_ads(customer_id=req.customer_id, operations=[op])
        
        return {
            "status": "success",
            "ad_group_id": req.ad_group_id,
            "ad_id": req.ad_id,
            "new_status": req.status,
            "resource_name": ad_group_ad_resource_name,
        }
    except GoogleAdsException as ex:
        import traceback
        traceback.print_exc()
        print(f"[UPDATE_AD_STATUS_ERROR] GoogleAdsException: {str(ex)}", flush=True)
        return {"status": "error", "error": str(ex), "type": "GoogleAdsException"}
    except Exception as ex:
        import traceback
        traceback.print_exc()
        print(f"[UPDATE_AD_STATUS_ERROR] {type(ex).__name__}: {str(ex)}", flush=True)
        return {"status": "error", "error": str(ex), "type": type(ex).__name__}


@app.post("/ads/update-final-url", dependencies=[Depends(require_api_key)])
def update_ad_final_url(req: UpdateAdFinalUrlRequest):
    """
    Update the final URL of an ad in an ad group.
    Replaces the existing final URL with the new one.
    """
    try:
        client = get_client()
        service = client.get_service("AdGroupAdService")
        
        # Construct the ad_group_ad resource name
        ad_group_ad_resource_name = f"customers/{req.customer_id}/adGroupAds/{req.ad_group_id}~{req.ad_id}"
        
        op = client.get_type("AdGroupAdOperation")
        ad_group_ad = op.update
        ad_group_ad.resource_name = ad_group_ad_resource_name
        
        # Clear existing final URLs and add new one
        ad_group_ad.ad.final_urls.clear()
        ad_group_ad.ad.final_urls.append(req.final_url)
        
        op.update_mask.paths.append("ad.final_urls")
        
        resp = service.mutate_ad_group_ads(customer_id=req.customer_id, operations=[op])
        
        return {
            "status": "success",
            "ad_group_id": req.ad_group_id,
            "ad_id": req.ad_id,
            "final_url": req.final_url,
            "resource_name": ad_group_ad_resource_name,
        }
    except GoogleAdsException as ex:
        import traceback
        traceback.print_exc()
        print(f"[UPDATE_AD_FINAL_URL_ERROR] GoogleAdsException: {str(ex)}", flush=True)
        return {"status": "error", "error": str(ex), "type": "GoogleAdsException"}
    except Exception as ex:
        import traceback
        traceback.print_exc()
        print(f"[UPDATE_AD_FINAL_URL_ERROR] {type(ex).__name__}: {str(ex)}", flush=True)
        return {"status": "error", "error": str(ex), "type": type(ex).__name__}


@app.post("/assets/update-sitelink-final-url", dependencies=[Depends(require_api_key)])
def update_sitelink_asset_final_url(req: UpdateSitelinkAssetFinalUrlRequest):
    """
    Update the final URL of a sitelink asset.
    Replaces the existing final URL with the new one.
    """
    try:
        client = get_client()
        asset_service = client.get_service("AssetService")
        
        op = client.get_type("AssetOperation")
        asset = op.update
        asset.resource_name = req.asset_resource_name
        
        # Clear existing final URLs and add new one
        asset.final_urls.clear()
        asset.final_urls.append(req.final_url)
        
        op.update_mask.paths.append("final_urls")
        
        resp = asset_service.mutate_assets(customer_id=req.customer_id, operations=[op])
        
        return {
            "status": "success",
            "asset_resource_name": req.asset_resource_name,
            "final_url": req.final_url,
        }
    except GoogleAdsException as ex:
        import traceback
        traceback.print_exc()
        print(f"[UPDATE_SITELINK_FINAL_URL_ERROR] GoogleAdsException: {str(ex)}", flush=True)
        return {"status": "error", "error": str(ex), "type": "GoogleAdsException"}
    except Exception as ex:
        import traceback
        traceback.print_exc()
        print(f"[UPDATE_SITELINK_FINAL_URL_ERROR] {type(ex).__name__}: {str(ex)}", flush=True)
        return {"status": "error", "error": str(ex), "type": type(ex).__name__}


@app.post("/ads/create-rsa", dependencies=[Depends(require_api_key)])
def create_rsa(req: CreateRsaRequest):
    """Create a Responsive Search Ad in an ad group."""
    client = get_client()
    service = client.get_service("AdGroupAdService")
    op = client.get_type("AdGroupAdOperation")
    ad_group_ad = op.create

    ad_group_ad.ad_group = req.ad_group_resource_name
    ad_group_ad.status = getattr(client.enums.AdGroupAdStatusEnum, req.status)

    # Build RSA
    ad = ad_group_ad.ad
    ad.final_urls.append(req.final_url)

    rsa = ad.responsive_search_ad

    # Add headlines (max 15, max 30 chars each)
    for headline_text in req.headlines[:15]:
        headline = client.get_type("AdTextAsset")
        headline.text = headline_text[:30]
        rsa.headlines.append(headline)

    # Add descriptions (max 4, max 90 chars each)
    for desc_text in req.descriptions[:4]:
        description = client.get_type("AdTextAsset")
        description.text = desc_text[:90]
        rsa.descriptions.append(description)

    try:
        resp = service.mutate_ad_group_ads(customer_id=req.customer_id, operations=[op])
        rn = resp.results[0].resource_name
        return {
            "resource_name": rn,
            "ad_group": req.ad_group_resource_name,
            "status": req.status,
            "headlines_count": len(req.headlines),
            "descriptions_count": len(req.descriptions),
        }
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


# ---------------------------------------------------------------------------
# Asset models
# ---------------------------------------------------------------------------

class CreateCallAssetRequest(BaseModel):
    customer_id: str
    phone_number: str
    country_code: str = Field("CA", description="ISO country code e.g. CA, US")
    campaign_id: Optional[str] = None
    ad_group_id: Optional[str] = None


class CreateSitelinkAssetRequest(BaseModel):
    customer_id: str
    link_text: str = Field(..., description="Sitelink display text (max 25 chars)")
    final_url: str
    description1: Optional[str] = Field(None, description="First description line (max 35 chars)")
    description2: Optional[str] = Field(None, description="Second description line (max 35 chars)")
    campaign_id: Optional[str] = None


class CreateCalloutAssetRequest(BaseModel):
    customer_id: str
    callout_text: str = Field(..., description="Callout text (max 25 chars)")
    campaign_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Asset endpoints
# ---------------------------------------------------------------------------

@app.post("/assets/create-call", dependencies=[Depends(require_api_key)])
def create_call_asset(req: CreateCallAssetRequest):
    """Create a call asset and optionally link it to a campaign."""
    client = get_client()
    asset_service = client.get_service("AssetService")
    asset_op = client.get_type("AssetOperation")
    asset = asset_op.create

    asset.call_asset.phone_number = req.phone_number
    asset.call_asset.country_code = req.country_code

    try:
        resp = asset_service.mutate_assets(customer_id=req.customer_id, operations=[asset_op])
        asset_rn = resp.results[0].resource_name

        # Link to campaign if provided
        if req.campaign_id:
            campaign_asset_service = client.get_service("CampaignAssetService")
            ca_op = client.get_type("CampaignAssetOperation")
            ca = ca_op.create
            ca.asset = asset_rn
            ca.field_type = client.enums.AssetFieldTypeEnum.CALL
            ca.campaign = client.get_service("CampaignService").campaign_path(
                req.customer_id, req.campaign_id
            )
            campaign_asset_service.mutate_campaign_assets(
                customer_id=req.customer_id, operations=[ca_op]
            )

        return {
            "resource_name": asset_rn,
            "phone_number": req.phone_number,
            "country_code": req.country_code,
            "linked_to_campaign": req.campaign_id,
        }
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


@app.post("/assets/update-call-asset-schedule", dependencies=[Depends(require_api_key)])
def update_call_asset_schedule(req: UpdateCallAssetScheduleRequest):
    """
    Update the schedule on a call asset to show the phone number only during specified hours.
    The call asset will be invisible outside these hours, but linked ads will still serve.
    """
    try:
        client = get_client()
        asset_service = client.get_service("AssetService")
        
        op = client.get_type("AssetOperation")
        asset = op.update
        asset.resource_name = req.call_asset_resource_name
        
        # Clear existing schedules and add new ones
        for schedule in req.schedules:
            ad_schedule = asset.ad_schedule_targets.add()
            ad_schedule.day_of_week = getattr(client.enums.DayOfWeekEnum, schedule.day_of_week)
            ad_schedule.start_hour = schedule.start_hour
            ad_schedule.start_minute = getattr(client.enums.MinuteOfHourEnum, schedule.start_minute)
            ad_schedule.end_hour = schedule.end_hour
            ad_schedule.end_minute = getattr(client.enums.MinuteOfHourEnum, schedule.end_minute)
        
        op.update_mask.paths.append("ad_schedule_targets")
        
        resp = asset_service.mutate_assets(customer_id=req.customer_id, operations=[op])
        
        scheduled_days = [s.day_of_week for s in req.schedules]
        
        return {
            "status": "success",
            "call_asset_resource_name": req.call_asset_resource_name,
            "scheduled_days": scheduled_days,
            "total_schedules": len(req.schedules),
            "note": "Call asset will only be visible during these hours. Linked ads will still serve outside these hours without the phone number.",
        }
    except GoogleAdsException as ex:
        import traceback
        traceback.print_exc()
        print(f"[UPDATE_CALL_ASSET_SCHEDULE_ERROR] GoogleAdsException: {str(ex)}", flush=True)
        return {"status": "error", "error": str(ex), "type": "GoogleAdsException"}
    except Exception as ex:
        import traceback
        traceback.print_exc()
        print(f"[UPDATE_CALL_ASSET_SCHEDULE_ERROR] {type(ex).__name__}: {str(ex)}", flush=True)
        return {"status": "error", "error": str(ex), "type": type(ex).__name__}


@app.post("/assets/create-sitelink", dependencies=[Depends(require_api_key)])
def create_sitelink_asset(req: CreateSitelinkAssetRequest):
    """Create a sitelink asset and optionally link it to a campaign."""
    client = get_client()
    asset_service = client.get_service("AssetService")
    asset_op = client.get_type("AssetOperation")
    asset = asset_op.create

    asset.sitelink_asset.link_text = req.link_text[:25]
    asset.final_urls.append(req.final_url)
    if req.description1:
        asset.sitelink_asset.description1 = req.description1[:35]
    if req.description2:
        asset.sitelink_asset.description2 = req.description2[:35]

    try:
        resp = asset_service.mutate_assets(customer_id=req.customer_id, operations=[asset_op])
        asset_rn = resp.results[0].resource_name

        if req.campaign_id:
            campaign_asset_service = client.get_service("CampaignAssetService")
            ca_op = client.get_type("CampaignAssetOperation")
            ca = ca_op.create
            ca.asset = asset_rn
            ca.field_type = client.enums.AssetFieldTypeEnum.SITELINK
            ca.campaign = client.get_service("CampaignService").campaign_path(
                req.customer_id, req.campaign_id
            )
            campaign_asset_service.mutate_campaign_assets(
                customer_id=req.customer_id, operations=[ca_op]
            )

        return {
            "resource_name": asset_rn,
            "link_text": req.link_text,
            "final_url": req.final_url,
            "linked_to_campaign": req.campaign_id,
        }
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


@app.post("/assets/create-callout", dependencies=[Depends(require_api_key)])
def create_callout_asset(req: CreateCalloutAssetRequest):
    """Create a callout asset and optionally link it to a campaign."""
    client = get_client()
    asset_service = client.get_service("AssetService")
    asset_op = client.get_type("AssetOperation")
    asset = asset_op.create

    asset.callout_asset.callout_text = req.callout_text[:25]

    try:
        resp = asset_service.mutate_assets(customer_id=req.customer_id, operations=[asset_op])
        asset_rn = resp.results[0].resource_name

        if req.campaign_id:
            campaign_asset_service = client.get_service("CampaignAssetService")
            ca_op = client.get_type("CampaignAssetOperation")
            ca = ca_op.create
            ca.asset = asset_rn
            ca.field_type = client.enums.AssetFieldTypeEnum.CALLOUT
            ca.campaign = client.get_service("CampaignService").campaign_path(
                req.customer_id, req.campaign_id
            )
            campaign_asset_service.mutate_campaign_assets(
                customer_id=req.customer_id, operations=[ca_op]
            )

        return {
            "resource_name": asset_rn,
            "callout_text": req.callout_text,
            "linked_to_campaign": req.campaign_id,
        }
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


class CreateStructuredSnippetAssetRequest(BaseModel):
    customer_id: str
    header: str = Field(..., description="Snippet header e.g. Services, Amenities, Brands")
    values: list[str] = Field(..., description="List of snippet values (max 10, each max 25 chars)")
    campaign_id: Optional[str] = None


class UpdateMobileBidModifierRequest(BaseModel):
    customer_id: str
    campaign_id: str
    modifier: float = Field(..., description="Bid modifier multiplier. 1.25 = +25%, 0.75 = -25%, 1.0 = no change")


@app.post("/assets/create-structured-snippet", dependencies=[Depends(require_api_key)])
def create_structured_snippet_asset(req: CreateStructuredSnippetAssetRequest):
    """Create a structured snippet asset and optionally link it to a campaign."""
    client = get_client()
    asset_service = client.get_service("AssetService")
    asset_op = client.get_type("AssetOperation")
    asset = asset_op.create

    asset.structured_snippet_asset.header = req.header
    for value in req.values[:10]:
        asset.structured_snippet_asset.values.append(value[:25])

    try:
        resp = asset_service.mutate_assets(customer_id=req.customer_id, operations=[asset_op])
        asset_rn = resp.results[0].resource_name

        if req.campaign_id:
            campaign_asset_service = client.get_service("CampaignAssetService")
            ca_op = client.get_type("CampaignAssetOperation")
            ca = ca_op.create
            ca.asset = asset_rn
            ca.field_type = client.enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET
            ca.campaign = client.get_service("CampaignService").campaign_path(
                req.customer_id, req.campaign_id
            )
            campaign_asset_service.mutate_campaign_assets(
                customer_id=req.customer_id, operations=[ca_op]
            )

        return {
            "resource_name": asset_rn,
            "header": req.header,
            "values": req.values,
            "linked_to_campaign": req.campaign_id,
        }
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


class RemoveCampaignAssetRequest(BaseModel):
    campaign_asset_resource_name: str = Field(
        ...,
        description="Full resource name: customers/{customer_id}/campaignAssets/{campaign_id}~{asset_id}~{field_type}"
    )


@app.post("/assets/remove-campaign-asset", dependencies=[Depends(require_api_key)])
def remove_campaign_asset(req: RemoveCampaignAssetRequest):
    """Unlink an asset from a campaign. Asset stays in the account but stops showing."""
    customer_id = req.campaign_asset_resource_name.split("/")[1]
    client = get_client()
    service = client.get_service("CampaignAssetService")
    op = client.get_type("CampaignAssetOperation")
    op.remove = req.campaign_asset_resource_name

    try:
        service.mutate_campaign_assets(customer_id=customer_id, operations=[op])
        return {"status": "success", "removed": req.campaign_asset_resource_name}
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


class RemoveCampaignImageAssetRequest(BaseModel):
    customer_id: str
    campaign_id: str
    asset_id: str = Field(..., description="Numeric asset ID — found via read MCP campaign_asset query")


@app.post("/assets/remove-campaign-image-asset", dependencies=[Depends(require_api_key)])
def remove_campaign_image_asset(req: RemoveCampaignImageAssetRequest):
    """Remove an image asset from a campaign by asset ID. Constructs the resource name internally."""
    resource_name = (
        f"customers/{req.customer_id}/campaignAssets/"
        f"{req.campaign_id}~{req.asset_id}~IMAGE"
    )
    client = get_client()
    service = client.get_service("CampaignAssetService")
    op = client.get_type("CampaignAssetOperation")
    op.remove = resource_name

    try:
        service.mutate_campaign_assets(customer_id=req.customer_id, operations=[op])
        return {"status": "success", "removed": resource_name}
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


@app.get("/campaigns/stats", dependencies=[Depends(require_api_key)])
def get_campaign_stats(customer_id: str, campaign_id: str, period: str = "LAST_7_DAYS"):
    """
    Comprehensive campaign stats — runs 9 sub-queries covering all available
    Google Ads dimensions: daily, device, network, hour, day-of-week,
    keywords, search terms, gender, and age range.
    Each sub-query fails gracefully — others still return.
    """
    client = get_client()
    ga_service = client.get_service("GoogleAdsService")

    def run(query):
        try:
            return list(ga_service.search(customer_id=customer_id, query=query))
        except Exception as e:
            return []

    def micros(v):
        return round(v / 1_000_000, 2) if v else 0

    def pct(v):
        return round(v * 100, 2) if v and v > 0 else 0

    def impression_share(v):
        # Google returns -1 for unavailable, 0.1 minimum shown as "<10%"
        if v is None or v < 0:
            return None
        return round(v * 100, 1)

    # ── Q1: Daily base performance ────────────────────────────────────────
    q_daily = f"""
        SELECT
            campaign.id, campaign.name, campaign.status,
            campaign.bidding_strategy_type,
            metrics.impressions, metrics.clicks, metrics.ctr,
            metrics.average_cpc, metrics.cost_micros,
            metrics.conversions, metrics.all_conversions,
            metrics.search_impression_share,
            metrics.search_absolute_top_impression_share,
            metrics.search_top_impression_share,
            metrics.search_budget_lost_impression_share,
            metrics.search_rank_lost_impression_share,
            metrics.phone_calls, metrics.phone_impressions,
            metrics.phone_through_rate,
            metrics.invalid_clicks,
            segments.date
        FROM campaign
        WHERE campaign.id = '{campaign_id}'
          AND segments.date DURING {period}
        ORDER BY segments.date DESC
    """

    # ── Q2: Device breakdown ──────────────────────────────────────────────
    q_device = f"""
        SELECT
            metrics.impressions, metrics.clicks, metrics.ctr,
            metrics.average_cpc, metrics.cost_micros, metrics.conversions,
            segments.device
        FROM campaign
        WHERE campaign.id = '{campaign_id}'
          AND segments.date DURING {period}
    """

    # ── Q3: Ad network type ───────────────────────────────────────────────
    q_network = f"""
        SELECT
            metrics.impressions, metrics.clicks, metrics.ctr,
            metrics.average_cpc, metrics.cost_micros, metrics.conversions,
            segments.ad_network_type
        FROM campaign
        WHERE campaign.id = '{campaign_id}'
          AND segments.date DURING {period}
    """

    # ── Q4: Hour of day ───────────────────────────────────────────────────
    q_hour = f"""
        SELECT
            metrics.impressions, metrics.clicks, metrics.ctr,
            metrics.average_cpc, metrics.cost_micros,
            segments.hour
        FROM campaign
        WHERE campaign.id = '{campaign_id}'
          AND segments.date DURING {period}
    """

    # ── Q5: Day of week (last 30 days for more data) ──────────────────────
    q_dow = f"""
        SELECT
            metrics.impressions, metrics.clicks, metrics.ctr,
            metrics.average_cpc, metrics.cost_micros, metrics.conversions,
            segments.day_of_week
        FROM campaign
        WHERE campaign.id = '{campaign_id}'
          AND segments.date DURING LAST_30_DAYS
    """

    # ── Q6: Keyword performance ───────────────────────────────────────────
    q_keywords = f"""
        SELECT
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            ad_group_criterion.status,
            ad_group_criterion.quality_info.quality_score,
            ad_group_criterion.quality_info.search_predicted_ctr,
            ad_group_criterion.quality_info.ad_relevance,
            ad_group_criterion.quality_info.landing_page_experience,
            ad_group.name,
            metrics.impressions, metrics.clicks, metrics.ctr,
            metrics.average_cpc, metrics.cost_micros, metrics.conversions,
            metrics.search_impression_share
        FROM keyword_view
        WHERE campaign.id = '{campaign_id}'
          AND segments.date DURING {period}
        ORDER BY metrics.clicks DESC
        LIMIT 100
    """

    # ── Q7: Search terms (what people actually typed) ─────────────────────
    q_search_terms = f"""
        SELECT
            search_term_view.search_term,
            search_term_view.status,
            metrics.impressions, metrics.clicks, metrics.ctr,
            metrics.average_cpc, metrics.cost_micros, metrics.conversions
        FROM search_term_view
        WHERE campaign.id = '{campaign_id}'
          AND segments.date DURING {period}
        ORDER BY metrics.clicks DESC
        LIMIT 100
    """

    # ── Q8: Gender (note: often UNDETERMINED for healthcare) ─────────────
    q_gender = f"""
        SELECT
            ad_group_criterion.gender.type,
            metrics.impressions, metrics.clicks, metrics.ctr,
            metrics.average_cpc, metrics.cost_micros
        FROM gender_view
        WHERE campaign.id = '{campaign_id}'
          AND segments.date DURING {period}
    """

    # ── Q9: Age range ─────────────────────────────────────────────────────
    q_age = f"""
        SELECT
            ad_group_criterion.age_range.type,
            metrics.impressions, metrics.clicks, metrics.ctr,
            metrics.average_cpc, metrics.cost_micros
        FROM age_range_view
        WHERE campaign.id = '{campaign_id}'
          AND segments.date DURING {period}
    """

    # Run all queries
    daily_rows    = run(q_daily)
    device_rows   = run(q_device)
    network_rows  = run(q_network)
    hour_rows     = run(q_hour)
    dow_rows      = run(q_dow)
    kw_rows       = run(q_keywords)
    st_rows       = run(q_search_terms)
    gender_rows   = run(q_gender)
    age_rows      = run(q_age)

    # ── Process daily ─────────────────────────────────────────────────────
    daily = []
    for r in daily_rows:
        daily.append({
            "date":                          r.segments.date,
            "campaign_name":                 r.campaign.name,
            "campaign_status":               r.campaign.status.name,
            "bidding_strategy":              r.campaign.bidding_strategy_type.name,
            "impressions":                   r.metrics.impressions,
            "clicks":                        r.metrics.clicks,
            "ctr_pct":                       pct(r.metrics.ctr),
            "avg_cpc":                       micros(r.metrics.average_cpc),
            "cost":                          micros(r.metrics.cost_micros),
            "conversions":                   round(r.metrics.conversions, 1),
            "all_conversions":               round(r.metrics.all_conversions, 1),
            "search_impression_share_pct":   impression_share(r.metrics.search_impression_share),
            "abs_top_impression_share_pct":  impression_share(r.metrics.search_absolute_top_impression_share),
            "top_impression_share_pct":      impression_share(r.metrics.search_top_impression_share),
            "budget_lost_is_pct":            impression_share(r.metrics.search_budget_lost_impression_share),
            "rank_lost_is_pct":              impression_share(r.metrics.search_rank_lost_impression_share),
            "phone_calls":                   r.metrics.phone_calls,
            "phone_impressions":             r.metrics.phone_impressions,
            "phone_through_rate_pct":        pct(r.metrics.phone_through_rate),
            "invalid_clicks":                r.metrics.invalid_clicks,
        })

    # Summary totals
    ti = sum(r["impressions"] for r in daily)
    tc = sum(r["clicks"] for r in daily)
    cost = round(sum(r["cost"] for r in daily), 2)
    conv = round(sum(r["conversions"] for r in daily), 1)

    # ── Process device ────────────────────────────────────────────────────
    devices = {}
    for r in device_rows:
        d = r.segments.device.name
        devices.setdefault(d, {"impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0})
        devices[d]["impressions"] += r.metrics.impressions
        devices[d]["clicks"]      += r.metrics.clicks
        devices[d]["cost"]        += micros(r.metrics.cost_micros)
        devices[d]["conversions"] += round(r.metrics.conversions, 1)
    for d in devices:
        i, c = devices[d]["impressions"], devices[d]["clicks"]
        devices[d]["ctr_pct"] = round((c / i * 100) if i else 0, 2)
        devices[d]["avg_cpc"] = round((devices[d]["cost"] / c) if c else 0, 2)

    # ── Process network ───────────────────────────────────────────────────
    networks = {}
    for r in network_rows:
        n = r.segments.ad_network_type.name
        networks.setdefault(n, {"impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0})
        networks[n]["impressions"] += r.metrics.impressions
        networks[n]["clicks"]      += r.metrics.clicks
        networks[n]["cost"]        += micros(r.metrics.cost_micros)
        networks[n]["conversions"] += round(r.metrics.conversions, 1)

    # ── Process hourly ────────────────────────────────────────────────────
    hours = {}
    for r in hour_rows:
        h = r.segments.hour
        hours.setdefault(h, {"impressions": 0, "clicks": 0, "cost": 0.0})
        hours[h]["impressions"] += r.metrics.impressions
        hours[h]["clicks"]      += r.metrics.clicks
        hours[h]["cost"]        += micros(r.metrics.cost_micros)
    by_hour = [{"hour": h, **hours[h]} for h in sorted(hours)]

    # ── Process day of week ───────────────────────────────────────────────
    dow = {}
    for r in dow_rows:
        day = r.segments.day_of_week.name
        dow.setdefault(day, {"impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0})
        dow[day]["impressions"] += r.metrics.impressions
        dow[day]["clicks"]      += r.metrics.clicks
        dow[day]["cost"]        += micros(r.metrics.cost_micros)
        dow[day]["conversions"] += round(r.metrics.conversions, 1)

    # ── Process keywords ──────────────────────────────────────────────────
    keywords = []
    for r in kw_rows:
        keywords.append({
            "keyword":               r.ad_group_criterion.keyword.text,
            "match_type":            r.ad_group_criterion.keyword.match_type.name,
            "status":                r.ad_group_criterion.status.name,
            "ad_group":              r.ad_group.name,
            "quality_score":         r.ad_group_criterion.quality_info.quality_score or None,
            "predicted_ctr":         r.ad_group_criterion.quality_info.search_predicted_ctr.name if r.ad_group_criterion.quality_info.search_predicted_ctr else None,
            "ad_relevance":          r.ad_group_criterion.quality_info.ad_relevance.name if r.ad_group_criterion.quality_info.ad_relevance else None,
            "landing_page_exp":      r.ad_group_criterion.quality_info.landing_page_experience.name if r.ad_group_criterion.quality_info.landing_page_experience else None,
            "impressions":           r.metrics.impressions,
            "clicks":                r.metrics.clicks,
            "ctr_pct":               pct(r.metrics.ctr),
            "avg_cpc":               micros(r.metrics.average_cpc),
            "cost":                  micros(r.metrics.cost_micros),
            "conversions":           round(r.metrics.conversions, 1),
            "impression_share_pct":  impression_share(r.metrics.search_impression_share),
        })

    # ── Process search terms ──────────────────────────────────────────────
    search_terms = []
    for r in st_rows:
        search_terms.append({
            "search_term":  r.search_term_view.search_term,
            "status":       r.search_term_view.status.name,
            "impressions":  r.metrics.impressions,
            "clicks":       r.metrics.clicks,
            "ctr_pct":      pct(r.metrics.ctr),
            "avg_cpc":      micros(r.metrics.average_cpc),
            "cost":         micros(r.metrics.cost_micros),
            "conversions":  round(r.metrics.conversions, 1),
        })

    # ── Process gender ────────────────────────────────────────────────────
    genders = {}
    for r in gender_rows:
        g = r.ad_group_criterion.gender.type_.name
        genders.setdefault(g, {"impressions": 0, "clicks": 0, "cost": 0.0})
        genders[g]["impressions"] += r.metrics.impressions
        genders[g]["clicks"]      += r.metrics.clicks
        genders[g]["cost"]        += micros(r.metrics.cost_micros)

    # ── Process age range ─────────────────────────────────────────────────
    ages = {}
    for r in age_rows:
        a = r.ad_group_criterion.age_range.type_.name
        ages.setdefault(a, {"impressions": 0, "clicks": 0, "cost": 0.0})
        ages[a]["impressions"] += r.metrics.impressions
        ages[a]["clicks"]      += r.metrics.clicks
        ages[a]["cost"]        += micros(r.metrics.cost_micros)

    return {
        "customer_id":  customer_id,
        "campaign_id":  campaign_id,
        "summary": {
            "period":       period,
            "impressions":  ti,
            "clicks":       tc,
            "ctr_pct":      round((tc / ti * 100) if ti else 0, 2),
            "avg_cpc":      round((cost / tc) if tc else 0, 2),
            "total_cost":   cost,
            "conversions":  conv,
        },
        "daily":           daily,
        "by_device":       devices,
        "by_network":      networks,
        "by_hour":         by_hour,
        "by_day_of_week":  dow,
        "keywords":        keywords,
        "search_terms":    search_terms,
        "demographics": {
            "gender":    genders,
            "age_range": ages,
        },
    }


class UpdateAdScheduleRequest(BaseModel):
    customer_id: str
    campaign_id: str
    old_criterion_resource_name: str = Field(
        ...,
        description="Resource name of the existing ad schedule to remove. Get from read MCP campaign_criterion query."
    )
    day_of_week: str = Field("SUNDAY", description="MONDAY through SUNDAY")
    start_hour: int = Field(..., description="Start hour 0-23 (e.g. 8 for 8am)")
    start_minute: str = Field("ZERO", description="ZERO, FIFTEEN, THIRTY, or FORTY_FIVE")
    end_hour: int = Field(..., description="End hour 0-24 (e.g. 14 for 2pm)")
    end_minute: str = Field("ZERO", description="ZERO, FIFTEEN, THIRTY, or FORTY_FIVE")


class UpdateConversionActionCallDurationRequest(BaseModel):
    customer_id: str
    conversion_action_id: str = Field(
        ..., description="Numeric conversion action ID — get from read MCP conversion_action query"
    )
    phone_call_duration_seconds: int = Field(
        0, description="Minimum call duration in seconds to count as conversion. 0 = capture every call attempt."
    )


class CreatePhoneCallConversionRequest(BaseModel):
    customer_id: str
    campaign_id: str = Field(..., description="Numeric campaign ID")
    conversion_name: str = Field(..., description="Name of the conversion action (e.g., 'My Business - Phone Call')")


class CreateFormSubmissionConversionRequest(BaseModel):
    customer_id: str
    campaign_id: str = Field(..., description="Numeric campaign ID")
    conversion_name: str = Field(..., description="Name of the conversion action (e.g., 'My Business - Form Submission')")
    form_page_url: str = Field(..., description="URL of the form page (e.g., 'https://example.com/contact')")


class AddLocationCriterionRequest(BaseModel):
    customer_id: str
    campaign_id: str = Field(..., description="Numeric campaign ID")
    locations: list[str] = Field(..., description="List of location names (e.g., ['Calgary, Alberta', 'Edmonton, Alberta', 'Texas'])")
    country_code: str = Field("CA", description="Country code for geo lookup (e.g., 'CA' for Canada, 'US' for United States). Defaults to CA.")


class RemoveLocationCriterionRequest(BaseModel):
    customer_id: str
    campaign_id: str = Field(..., description="Numeric campaign ID")
    locations: list[str] = Field(..., description="List of location names to remove (e.g., ['Calgary, Alberta', 'Edmonton, Alberta'])")


class AddProximityRadiusRequest(BaseModel):
    customer_id: str
    campaign_id: str = Field(..., description="Numeric campaign ID")
    latitude: float = Field(..., description="Latitude of the center point")
    longitude: float = Field(..., description="Longitude of the center point")
    radius_km: int = Field(..., description="Radius in kilometers (1-50)")


class ScheduleSlot(BaseModel):
    day_of_week: str = Field(..., description="MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY")
    start_hour: int = Field(..., description="Start hour 0-23 (e.g., 7 for 7am)")
    end_hour: int = Field(..., description="End hour 0-24 (e.g., 19 for 7pm)")
    start_minute: str = Field("ZERO", description="ZERO, FIFTEEN, THIRTY, or FORTY_FIVE")
    end_minute: str = Field("ZERO", description="ZERO, FIFTEEN, THIRTY, or FORTY_FIVE")


class CreateAdScheduleRequest(BaseModel):
    customer_id: str
    campaign_id: str = Field(..., description="Numeric campaign ID")
    schedules: list[ScheduleSlot] = Field(..., description="List of ad schedule time slots")


class DeleteAdScheduleRequest(BaseModel):
    customer_id: str
    campaign_id: str = Field(..., description="Numeric campaign ID")
    days_of_week: list[str] = Field(..., description="List of days to remove (e.g., ['MONDAY', 'FRIDAY']). Removes all schedules for these days.")


class CreateDemographicCriterionRequest(BaseModel):
    customer_id: str
    ad_group_id: str = Field(..., description="Numeric ad group ID")
    demographic_type: str = Field(..., description="AGE_RANGE or GENDER")
    demographic_value: str = Field(
        ...,
        description="For AGE_RANGE: AGE_RANGE_18_24, AGE_RANGE_25_34, AGE_RANGE_35_44, AGE_RANGE_45_54, AGE_RANGE_55_64, AGE_RANGE_65_UP. For GENDER: MALE, FEMALE, UNDETERMINED."
    )
    bid_modifier: float = Field(
        1.0,
        description="Bid modifier. 1.5 = +50%, 0.8 = -20%, 0.0 = exclude. Default 1.0 = no change."
    )


@app.post("/ad-groups/create-demographic-criterion", dependencies=[Depends(require_api_key)])
def create_demographic_criterion(req: CreateDemographicCriterionRequest):
    """
    Create a new demographic criterion (age range or gender) on an ad group with a bid modifier.
    Use when the demographic doesn't exist yet and needs to be added.
    """
    client = get_client()
    service = client.get_service("AdGroupCriterionService")
    op = client.get_type("AdGroupCriterionOperation")
    criterion = op.create
    criterion.ad_group = f"customers/{req.customer_id}/adGroups/{req.ad_group_id}"
    criterion.bid_modifier = req.bid_modifier

    if req.demographic_type == "AGE_RANGE":
        criterion.age_range.type_ = getattr(
            client.enums.AgeRangeTypeEnum, req.demographic_value
        )
    elif req.demographic_type == "GENDER":
        criterion.gender.type_ = getattr(
            client.enums.GenderTypeEnum, req.demographic_value
        )
    else:
        raise HTTPException(status_code=400, detail="demographic_type must be AGE_RANGE or GENDER")

    try:
        resp = service.mutate_ad_group_criteria(customer_id=req.customer_id, operations=[op])
        return {
            "status": "success",
            "resource_name": resp.results[0].resource_name,
            "demographic_type": req.demographic_type,
            "demographic_value": req.demographic_value,
            "bid_modifier": req.bid_modifier,
        }
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


class UpdateDemographicBidModifierRequest(BaseModel):
    customer_id: str
    ad_group_criterion_resource_name: str = Field(
        ...,
        description="Full resource name of the demographic criterion. Get from read MCP ad_group_criterion query filtering by age_range or gender type."
    )
    bid_modifier: float = Field(
        ...,
        description="Bid modifier multiplier. 1.5 = +50%, 0.8 = -20%, 0.0 = exclude this demographic entirely."
    )


@app.post("/ad-groups/update-demographic-bid-modifier", dependencies=[Depends(require_api_key)])
def update_demographic_bid_modifier(req: UpdateDemographicBidModifierRequest):
    """
    Update bid modifier for a demographic criterion (age range or gender) at ad group level.
    Works for any demographic type — Cowork identifies the criterion resource name via read MCP first.
    """
    client = get_client()
    service = client.get_service("AdGroupCriterionService")
    op = client.get_type("AdGroupCriterionOperation")
    op.update.resource_name = req.ad_group_criterion_resource_name
    op.update.bid_modifier = req.bid_modifier
    op.update_mask.paths.append("bid_modifier")
    try:
        service.mutate_ad_group_criteria(customer_id=req.customer_id, operations=[op])
        return {
            "status": "success",
            "criterion_resource_name": req.ad_group_criterion_resource_name,
            "bid_modifier": req.bid_modifier,
        }
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


@app.post("/conversions/update-call-duration", dependencies=[Depends(require_api_key)])
def update_conversion_action_call_duration(req: UpdateConversionActionCallDurationRequest):
    """Update the minimum phone call duration for a call conversion action."""
    client = get_client()
    service = client.get_service("ConversionActionService")
    op = client.get_type("ConversionActionOperation")
    op.update.resource_name = f"customers/{req.customer_id}/conversionActions/{req.conversion_action_id}"
    op.update.phone_call_duration_seconds = req.phone_call_duration_seconds
    op.update_mask.paths.append("phone_call_duration_seconds")
    try:
        service.mutate_conversion_actions(customer_id=req.customer_id, operations=[op])
        return {
            "status": "success",
            "conversion_action_id": req.conversion_action_id,
            "phone_call_duration_seconds": req.phone_call_duration_seconds,
        }
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


@app.post("/conversions/create-phone-call-conversion", dependencies=[Depends(require_api_key)])
def create_phone_call_conversion(req: CreatePhoneCallConversionRequest):
    """
    Create a phone call conversion action tracking calls 30+ seconds.
    Campaign-level conversion action that tracks phone call conversions.
    """
    try:
        client = get_client()
        service = client.get_service("ConversionActionService")
        op = client.get_type("ConversionActionOperation")
        conversion_action = op.create
        
        conversion_action.name = req.conversion_name
        conversion_action.status = client.enums.ConversionActionStatusEnum.ENABLED
        conversion_action.type_ = client.enums.ConversionActionTypeEnum.AD_CALL
        conversion_action.category = client.enums.ConversionActionCategoryEnum.PHONE_CALL_LEAD
        conversion_action.phone_call_duration_seconds = 30
        conversion_action.counting_type = client.enums.ConversionActionCountingTypeEnum.ONE_PER_CLICK
        
        resp = service.mutate_conversion_actions(customer_id=req.customer_id, operations=[op])
        conversion_action_id = resp.results[0].resource_name.split("/")[-1]
        return {
            "status": "success",
            "conversion_action_id": conversion_action_id,
            "conversion_name": req.conversion_name,
            "type": "PHONE_CALL_TWO_WAY",
            "category": "PHONE_CALL_LEAD",
            "phone_call_duration_seconds": 30,
            "campaign_id": req.campaign_id,
        }
    except GoogleAdsException as ex:
        import traceback
        traceback.print_exc()
        print(f"[PHONE_CALL_CONVERSION_ERROR] GoogleAdsException: {str(ex)}", flush=True)
        return {"status": "error", "error": str(ex), "type": "GoogleAdsException"}
    except Exception as ex:
        import traceback
        traceback.print_exc()
        print(f"[PHONE_CALL_CONVERSION_ERROR] {type(ex).__name__}: {str(ex)}", flush=True)
        return {"status": "error", "error": str(ex), "type": type(ex).__name__}


@app.post("/conversions/create-form-submission-conversion", dependencies=[Depends(require_api_key)])
def create_form_submission_conversion(req: CreateFormSubmissionConversionRequest):
    """
    Create a form submission conversion action tracking form submissions.
    Campaign-level conversion action that tracks webpage visits/submissions.
    Note: Page conditions (URL targeting) are configured when placing the conversion tag on the website, not here.
    """
    try:
        client = get_client()
        service = client.get_service("ConversionActionService")
        op = client.get_type("ConversionActionOperation")
        conversion_action = op.create
        
        conversion_action.name = req.conversion_name
        conversion_action.status = client.enums.ConversionActionStatusEnum.ENABLED
        conversion_action.type_ = client.enums.ConversionActionTypeEnum.WEBPAGE
        conversion_action.category = client.enums.ConversionActionCategoryEnum.SUBMIT_LEAD_FORM
        conversion_action.counting_type = client.enums.ConversionActionCountingTypeEnum.ONE_PER_CLICK
        
        resp = service.mutate_conversion_actions(customer_id=req.customer_id, operations=[op])
        conversion_action_id = resp.results[0].resource_name.split("/")[-1]
        return {
            "status": "success",
            "conversion_action_id": conversion_action_id,
            "conversion_name": req.conversion_name,
            "type": "WEBPAGE",
            "category": "SUBMIT_LEAD_FORM",
            "form_page_url": req.form_page_url,
            "note": "Place the conversion tag on " + req.form_page_url + " to track conversions on this page",
            "campaign_id": req.campaign_id,
        }
    except GoogleAdsException as ex:
        import traceback
        traceback.print_exc()
        print(f"[FORM_SUBMISSION_CONVERSION_ERROR] GoogleAdsException: {str(ex)}", flush=True)
        return {"status": "error", "error": str(ex), "type": "GoogleAdsException"}
    except Exception as ex:
        import traceback
        traceback.print_exc()
        print(f"[FORM_SUBMISSION_CONVERSION_ERROR] {type(ex).__name__}: {str(ex)}", flush=True)
        return {"status": "error", "error": str(ex), "type": type(ex).__name__}


@app.post("/locations/add-location-criterion", dependencies=[Depends(require_api_key)])
def add_location_criterion(req: AddLocationCriterionRequest):
    """
    Add location targeting to a campaign by location name(s).
    Dynamically looks up geo target constants by location name.
    Targets people in or regularly in the location (PRESENCE targeting).
    """
    client = get_client()
    service = client.get_service("CampaignCriterionService")
    google_ads_service = client.get_service("GoogleAdsService")
    
    added_locations = []
    errors = []
    
    for location_name in req.locations:
        try:
            # Extract city name (before comma if present)
            city = location_name.split(',')[0].strip()
            
            # Search for geo target constant by name using GoogleAdsService
            # Use proper GAQL with escaping and specified country code
            query = f"SELECT geo_target_constant.id, geo_target_constant.name FROM geo_target_constant WHERE geo_target_constant.name = '{city}' AND geo_target_constant.country_code = '{req.country_code}' LIMIT 1"
            response = google_ads_service.search(customer_id=req.customer_id, query=query)
            
            if not response.results:
                errors.append({"location": location_name, "error": f"Location '{city}' not found in {req.country_code} geo target database"})
                continue
            
            geo_target_id = response.results[0].geo_target_constant.id
            
            # Create campaign criterion for the location
            op = client.get_type("CampaignCriterionOperation")
            criterion = op.create
            criterion.campaign = f"customers/{req.customer_id}/campaigns/{req.campaign_id}"
            criterion.location.geo_target_constant = f"geoTargetConstants/{geo_target_id}"
            
            service.mutate_campaign_criteria(customer_id=req.customer_id, operations=[op])
            added_locations.append({"location": location_name, "geo_target_id": geo_target_id})
            
        except GoogleAdsException as ex:
            errors.append({"location": location_name, "error": str(ex)})
        except Exception as ex:
            errors.append({"location": location_name, "error": str(ex)})
    
    return {
        "status": "success" if not errors else "partial",
        "campaign_id": req.campaign_id,
        "added_locations": added_locations,
        "errors": errors if errors else None,
    }


@app.post("/locations/remove-location-criterion", dependencies=[Depends(require_api_key)])
def remove_location_criterion(req: RemoveLocationCriterionRequest):
    """
    Remove location targeting from a campaign by location name(s).
    Dynamically looks up geo target constants by location name and removes them.
    """
    client = get_client()
    service = client.get_service("CampaignCriterionService")
    google_ads_service = client.get_service("GoogleAdsService")
    
    removed_locations = []
    errors = []
    
    for location_name in req.locations:
        try:
            # Extract city name (before comma if present)
            city = location_name.split(',')[0].strip()
            
            # Search for geo target constant by name
            query = f"SELECT geo_target_constant.id, geo_target_constant.name FROM geo_target_constant WHERE geo_target_constant.name = '{city}' AND geo_target_constant.country_code = 'CA' LIMIT 1"
            response = google_ads_service.search(customer_id=req.customer_id, query=query)
            
            if not response.results:
                errors.append({"location": location_name, "error": f"Location '{city}' not found in Canada geo target database"})
                continue
            
            geo_target_id = response.results[0].geo_target_constant.id
            
            # Build resource name for the campaign criterion to remove
            criterion_resource_name = f"customers/{req.customer_id}/campaignCriteria/{req.campaign_id}~{geo_target_id}"
            
            # Create remove operation
            op = client.get_type("CampaignCriterionOperation")
            op.remove = criterion_resource_name
            
            service.mutate_campaign_criteria(customer_id=req.customer_id, operations=[op])
            removed_locations.append({"location": location_name, "geo_target_id": geo_target_id})
            
        except GoogleAdsException as ex:
            errors.append({"location": location_name, "error": str(ex)})
        except Exception as ex:
            errors.append({"location": location_name, "error": str(ex)})
    
    return {
        "status": "success" if not errors else "partial",
        "campaign_id": req.campaign_id,
        "removed_locations": removed_locations,
        "errors": errors if errors else None,
    }


@app.post("/locations/add-proximity-radius", dependencies=[Depends(require_api_key)])
def add_proximity_radius(req: AddProximityRadiusRequest):
    """
    Add proximity targeting to a campaign.
    Targets people within a radius (in km) of a center point (latitude/longitude).
    Radius must be 1-50 km.
    """
    try:
        client = get_client()
        service = client.get_service("CampaignCriterionService")
        
        # Validate radius
        if req.radius_km < 1 or req.radius_km > 50:
            return {"status": "error", "error": "Radius must be between 1 and 50 km"}
        
        # Create proximity criterion
        op = client.get_type("CampaignCriterionOperation")
        criterion = op.create
        criterion.campaign = f"customers/{req.customer_id}/campaigns/{req.campaign_id}"
        
        proximity = criterion.proximity
        proximity.geo_point.latitude_in_micro_degrees = int(req.latitude * 1_000_000)
        proximity.geo_point.longitude_in_micro_degrees = int(req.longitude * 1_000_000)
        proximity.radius = req.radius_km
        proximity.radius_units = client.enums.ProximityRadiusUnitsEnum.KILOMETERS
        
        service.mutate_campaign_criteria(customer_id=req.customer_id, operations=[op])
        
        return {
            "status": "success",
            "campaign_id": req.campaign_id,
            "proximity": {
                "latitude": req.latitude,
                "longitude": req.longitude,
                "radius_km": req.radius_km,
            },
            "note": "Ads will show to people within this radius of the center point",
        }
    except GoogleAdsException as ex:
        import traceback
        traceback.print_exc()
        print(f"[ADD_PROXIMITY_RADIUS_ERROR] GoogleAdsException: {str(ex)}", flush=True)
        return {"status": "error", "error": str(ex), "type": "GoogleAdsException"}
    except Exception as ex:
        import traceback
        traceback.print_exc()
        print(f"[ADD_PROXIMITY_RADIUS_ERROR] {type(ex).__name__}: {str(ex)}", flush=True)
        return {"status": "error", "error": str(ex), "type": type(ex).__name__}


@app.post("/campaigns/create-ad-schedule", dependencies=[Depends(require_api_key)])
def create_ad_schedule(req: CreateAdScheduleRequest):
    """
    Create ad schedule time slots for a campaign.
    Accepts multiple schedule slots (day + time range) in one call.
    Example: Mon-Fri 7am-7pm, Sat 9am-3pm.
    """
    client = get_client()
    service = client.get_service("CampaignCriterionService")
    
    created_schedules = []
    errors = []
    
    for schedule in req.schedules:
        try:
            op = client.get_type("CampaignCriterionOperation")
            criterion = op.create
            criterion.campaign = f"customers/{req.customer_id}/campaigns/{req.campaign_id}"
            
            # Set ad schedule info
            criterion.ad_schedule.day_of_week = getattr(
                client.enums.DayOfWeekEnum, schedule.day_of_week
            )
            criterion.ad_schedule.start_hour = schedule.start_hour
            criterion.ad_schedule.start_minute = getattr(
                client.enums.MinuteOfHourEnum, schedule.start_minute
            )
            criterion.ad_schedule.end_hour = schedule.end_hour
            criterion.ad_schedule.end_minute = getattr(
                client.enums.MinuteOfHourEnum, schedule.end_minute
            )
            
            service.mutate_campaign_criteria(customer_id=req.customer_id, operations=[op])
            created_schedules.append({
                "day_of_week": schedule.day_of_week,
                "start_time": f"{schedule.start_hour}:{schedule.start_minute}",
                "end_time": f"{schedule.end_hour}:{schedule.end_minute}",
            })
            
        except GoogleAdsException as ex:
            errors.append({
                "schedule": f"{schedule.day_of_week} {schedule.start_hour}:00-{schedule.end_hour}:00",
                "error": str(ex)
            })
        except Exception as ex:
            errors.append({
                "schedule": f"{schedule.day_of_week} {schedule.start_hour}:00-{schedule.end_hour}:00",
                "error": str(ex)
            })
    
    return {
        "status": "success" if not errors else "partial",
        "campaign_id": req.campaign_id,
        "created_schedules": created_schedules,
        "errors": errors if errors else None,
    }


@app.post("/campaigns/delete-ad-schedule", dependencies=[Depends(require_api_key)])
def delete_ad_schedule(req: DeleteAdScheduleRequest):
    """
    Delete ad schedules from a campaign by day of week.
    Queries all campaign criteria, finds ad schedules matching the provided days, and removes them.
    """
    try:
        client = get_client()
        service = client.get_service("CampaignCriterionService")
        google_ads_service = client.get_service("GoogleAdsService")
        
        # Query all campaign criteria to find ad schedules
        query = f"SELECT campaign_criterion.resource_name, campaign_criterion.ad_schedule.day_of_week FROM campaign_criterion WHERE campaign_criterion.campaign = 'customers/{req.customer_id}/campaigns/{req.campaign_id}' AND campaign_criterion.type = 'AD_SCHEDULE'"
        response = google_ads_service.search(customer_id=req.customer_id, query=query)
        
        removed_schedules = []
        errors = []
        operations = []
        
        # Convert input days to enum values for comparison
        days_to_remove = set()
        for day in req.days_of_week:
            try:
                day_enum = getattr(client.enums.DayOfWeekEnum, day)
                days_to_remove.add(day_enum)
            except AttributeError:
                errors.append({"day": day, "error": f"Invalid day of week: {day}"})
        
        # Find and mark matching schedules for removal
        for row in response.results:
            if row.campaign_criterion.ad_schedule.day_of_week in days_to_remove:
                op = client.get_type("CampaignCriterionOperation")
                op.remove = row.campaign_criterion.resource_name
                operations.append(op)
                
                removed_schedules.append({
                    "day_of_week": row.campaign_criterion.ad_schedule.day_of_week.name,
                    "start_hour": row.campaign_criterion.ad_schedule.start_hour,
                    "start_minute": row.campaign_criterion.ad_schedule.start_minute.name,
                    "end_hour": row.campaign_criterion.ad_schedule.end_hour,
                    "end_minute": row.campaign_criterion.ad_schedule.end_minute.name,
                })
        
        # Execute deletions if any found
        if operations:
            service.mutate_campaign_criteria(customer_id=req.customer_id, operations=operations)
        
        return {
            "status": "success" if not errors else "partial",
            "campaign_id": req.campaign_id,
            "removed_schedules": removed_schedules,
            "deleted_count": len(removed_schedules),
            "errors": errors if errors else None,
        }
    except GoogleAdsException as ex:
        import traceback
        traceback.print_exc()
        print(f"[DELETE_AD_SCHEDULE_ERROR] GoogleAdsException: {str(ex)}", flush=True)
        return {"status": "error", "error": str(ex), "type": "GoogleAdsException"}
    except Exception as ex:
        import traceback
        traceback.print_exc()
        print(f"[DELETE_AD_SCHEDULE_ERROR] {type(ex).__name__}: {str(ex)}", flush=True)
        return {"status": "error", "error": str(ex), "type": type(ex).__name__}


@app.post("/campaigns/update-ad-schedule", dependencies=[Depends(require_api_key)])
def update_ad_schedule(req: UpdateAdScheduleRequest):
    """
    Replace an ad schedule on a campaign.
    Removes the existing criterion and creates a new one with updated times.
    Both operations execute atomically in one API call.
    """
    client = get_client()
    service = client.get_service("CampaignCriterionService")

    # Operation 1 — remove existing schedule
    remove_op = client.get_type("CampaignCriterionOperation")
    remove_op.remove = req.old_criterion_resource_name

    # Operation 2 — create new schedule with updated times
    create_op = client.get_type("CampaignCriterionOperation")
    criterion = create_op.create
    criterion.campaign = f"customers/{req.customer_id}/campaigns/{req.campaign_id}"
    criterion.ad_schedule.day_of_week = getattr(client.enums.DayOfWeekEnum, req.day_of_week)
    criterion.ad_schedule.start_hour = req.start_hour
    criterion.ad_schedule.start_minute = getattr(client.enums.MinuteOfHourEnum, req.start_minute)
    criterion.ad_schedule.end_hour = req.end_hour
    criterion.ad_schedule.end_minute = getattr(client.enums.MinuteOfHourEnum, req.end_minute)

    try:
        resp = service.mutate_campaign_criteria(
            customer_id=req.customer_id,
            operations=[remove_op, create_op]
        )
        new_resource_name = next(
            (r.resource_name for r in resp.results if r.resource_name), None
        )
        return {
            "status": "success",
            "removed": req.old_criterion_resource_name,
            "new_criterion_resource_name": new_resource_name,
            "day_of_week": req.day_of_week,
            "start": f"{req.start_hour}:{req.start_minute}",
            "end": f"{req.end_hour}:{req.end_minute}",
        }
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


class UpdateGeoTargetTypeRequest(BaseModel):
    customer_id: str
    campaign_id: str
    positive_geo_target_type: str = Field(
        "PRESENCE",
        description="PRESENCE or PRESENCE_OR_INTEREST"
    )


@app.post("/campaigns/update-geo-target-type", dependencies=[Depends(require_api_key)])
def update_geo_target_type(req: UpdateGeoTargetTypeRequest):
    """Update campaign positive geo target type — PRESENCE or PRESENCE_OR_INTEREST."""
    client = get_client()
    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    op.update.resource_name = f"customers/{req.customer_id}/campaigns/{req.campaign_id}"
    op.update.geo_target_type_setting.positive_geo_target_type = getattr(
        client.enums.PositiveGeoTargetTypeEnum, req.positive_geo_target_type
    )
    op.update_mask.paths.append("geo_target_type_setting.positive_geo_target_type")
    try:
        service.mutate_campaigns(customer_id=req.customer_id, operations=[op])
        return {
            "status": "success",
            "campaign_id": req.campaign_id,
            "positive_geo_target_type": req.positive_geo_target_type,
        }
    except GoogleAdsException as ex:
        handle_gads_exception(ex)


@app.post("/campaigns/update-mobile-bid-modifier", dependencies=[Depends(require_api_key)])
def update_mobile_bid_modifier(req: UpdateMobileBidModifierRequest):
    """Update the mobile bid modifier for a campaign."""
    client = get_client()
    service = client.get_service("CampaignCriterionService")
    op = client.get_type("CampaignCriterionOperation")
    criterion = op.create

    criterion.campaign = client.get_service("CampaignService").campaign_path(
        req.customer_id, req.campaign_id
    )
    criterion.device.type_ = client.enums.DeviceEnum.MOBILE
    criterion.bid_modifier = req.modifier

    try:
        resp = service.mutate_campaign_criteria(
            customer_id=req.customer_id, operations=[op]
        )
        return {
            "resource_name": resp.results[0].resource_name,
            "campaign_id": req.campaign_id,
            "mobile_bid_modifier": req.modifier,
            "effect": f"{'+' if req.modifier >= 1 else ''}{round((req.modifier - 1) * 100)}%",
        }
    except GoogleAdsException as ex:
        handle_gads_exception(ex)
