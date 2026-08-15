"""GCPComputeClient dry-run flag (outstanding-decision #8)."""
import pytest

from hands.tools.gcp_api import GCPComputeClient


@pytest.mark.asyncio
async def test_start_preemptible_instances_defaults_to_dry_run():
    client = GCPComputeClient(project_id="test-proj", zone="us-central1-a")
    instances = await client.start_preemptible_instances(count=2, machine_type="n1-standard-4")

    assert len(instances) == 2
    assert all(i["dry_run"] is True for i in instances)


@pytest.mark.asyncio
async def test_start_preemptible_instances_tags_real_mode():
    client = GCPComputeClient(project_id="test-proj", zone="us-central1-a", dry_run=False)
    instances = await client.start_preemptible_instances(count=1, machine_type="n1-standard-4")

    assert instances[0]["dry_run"] is False
