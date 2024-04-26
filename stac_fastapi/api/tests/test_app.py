from datetime import datetime
from typing import List, Optional, Union

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from stac_pydantic import api

from stac_fastapi.api import app
from stac_fastapi.api.models import create_get_request_model, create_post_request_model
from stac_fastapi.extensions.core.filter.filter import FilterExtension
from stac_fastapi.types import stac
from stac_fastapi.types.config import ApiSettings
from stac_fastapi.types.core import NumType
from stac_fastapi.types.search import BaseSearchPostRequest


def test_client_response_type(TestCoreClient):
    """Test all GET endpoints. Verify that responses are valid STAC items."""

    test_app = app.StacApi(
        settings=ApiSettings(),
        client=TestCoreClient(),
    )

    with TestClient(test_app.app) as client:
        landing = client.get("/")
        collection = client.get("/collections/test")
        collections = client.get("/collections")
        item = client.get("/collections/test/items/test")
        item_collection = client.get(
            "/collections/test/items",
            params={"limit": 10},
        )
        get_search = client.get(
            "/search",
            params={
                "collections": ["test"],
            },
        )
        post_search = client.post(
            "/search",
            json={
                "collections": ["test"],
            },
        )

    assert landing.status_code == 200, landing.text
    api.LandingPage(**landing.json())

    assert collection.status_code == 200, collection.text
    api.Collection(**collection.json())

    assert collections.status_code == 200, collections.text
    api.collections.Collections(**collections.json())

    assert item.status_code == 200, item.text
    api.Item(**item.json())

    assert item_collection.status_code == 200, item_collection.text
    api.ItemCollection(**item_collection.json())

    assert get_search.status_code == 200, get_search.text
    api.ItemCollection(**get_search.json())

    assert post_search.status_code == 200, post_search.text
    api.ItemCollection(**post_search.json())


@pytest.mark.parametrize("validate", [True, False])
def test_client_invalid_response_type(validate, TestCoreClient, item_dict):
    """Check if the build in response validation switch works."""

    class InValidResponseClient(TestCoreClient):
        def get_item(self, item_id: str, collection_id: str, **kwargs) -> stac.Item:
            item_dict.pop("bbox")
            item_dict.pop("geometry")
            return stac.Item(**item_dict)

    test_app = app.StacApi(
        settings=ApiSettings(enable_response_models=validate),
        client=InValidResponseClient(),
    )

    with TestClient(test_app.app) as client:
        item = client.get("/collections/test/items/test")

    # Even if API validation passes, we should receive an invalid item
    if item.status_code == 200:
        with pytest.raises(ValidationError):
            api.Item(**item.json())

    # If internal validation is on, we should expect an internal error
    if validate:
        assert item.status_code == 500, item.text
    else:
        assert item.status_code == 200, item.text


def test_client_openapi(TestCoreClient):
    """Test if response models are all documented with OpenAPI."""

    test_app = app.StacApi(
        settings=ApiSettings(),
        client=TestCoreClient(),
    )
    test_app.app.openapi()
    components = ["LandingPage", "Collection", "Collections", "Item", "ItemCollection"]
    for component in components:
        assert component in test_app.app.openapi_schema["components"]["schemas"]


def test_filter_extension(TestCoreClient, item_dict):
    """Test if Filter Parameters are passed correctly."""

    class FilterClient(TestCoreClient):
        def post_search(
            self, search_request: BaseSearchPostRequest, **kwargs
        ) -> stac.ItemCollection:
            search_request.collections = ["test"]
            search_request.filter = {}
            search_request.filter_crs = "EPSG:4326"
            search_request.filter_lang = "cql2-text"

            return stac.ItemCollection(
                type="FeatureCollection", features=[stac.Item(**item_dict)]
            )

        def get_search(
            self,
            collections: Optional[List[str]] = None,
            ids: Optional[List[str]] = None,
            bbox: Optional[List[NumType]] = None,
            intersects: Optional[str] = None,
            datetime: Optional[Union[str, datetime]] = None,
            limit: Optional[int] = 10,
            filter: Optional[str] = None,
            filter_crs: Optional[str] = None,
            filter_lang: Optional[str] = None,
            **kwargs,
        ) -> stac.ItemCollection:
            # Check if all filter parameters are passed correctly

            assert filter == "TEST"

            # FIXME: https://github.com/stac-utils/stac-fastapi/issues/638
            # hyphen alias for filter_crs and filter_lang are currently not working
            # Query parameters `filter-crs` and `filter-lang`
            # should be recognized by the API
            # They are present in the `request.query_params` but not in the `kwargs`

            # assert filter_crs == "EPSG:4326"
            # assert filter_lang == "cql2-text"

            return stac.ItemCollection(
                type="FeatureCollection", features=[stac.Item(**item_dict)]
            )

    post_request_model = create_post_request_model([FilterExtension()])

    test_app = app.StacApi(
        settings=ApiSettings(),
        client=FilterClient(post_request_model=post_request_model),
        search_get_request_model=create_get_request_model([FilterExtension()]),
        search_post_request_model=post_request_model,
    )

    with TestClient(test_app.app) as client:
        get_search = client.get(
            "/search",
            params={
                "filter": "TEST",
                "filter-crs": "EPSG:4326",
                "filter-lang": "cql2-text",
            },
        )
        post_search = client.post(
            "/search",
            json={
                "collections": ["test"],
                "filter": {},
                "filter-crs": "EPSG:4326",
                "filter-lang": "cql2-text",
            },
        )

    assert get_search.status_code == 200, get_search.text
    assert post_search.status_code == 200, post_search.text
