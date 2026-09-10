"""Stable public Python API; implementation lives in responsibility-owned modules."""
from .common import (SLIDE_SCHEMA, STATE_SCHEMA, LEGACY_STATE_SCHEMAS, RECIPES, COMPONENT_ID, SLIDE_ID, HEX_COLOR, ALLOWED_OVERLAY_KEYS, ContractError)
from .overlays import (validate_tables, validate_objects, validate_text_boxes, validate_overlays, validate_text_marks, validate_chart_layout)
from .sources import (validate_slide_spec)
from .catalog import (load_catalog, catalog_revision, source_revisions, catalog_receipt)
from .state import (EditConflict, merge_state_snapshot, empty_state, reconcile_state, validate_state_snapshot)
