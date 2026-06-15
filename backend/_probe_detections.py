import asyncio
from app.agents.detection_agent import DetectionAgent
from app.splunk.mock_client import MockSplunkClient


async def main():
    agent = DetectionAgent(MockSplunkClient())
    dets = await agent.run()
    print("DETECTION_COUNT", len(dets))
    for d in dets:
        print(
            "DET",
            d.title,
            "| entity=", d.entity,
            "| events=", d.event_count,
            "| sev=", d.severity.value,
            "| mitre=", ",".join(d.mitre_tactics),
            "| ips=", ",".join(d.src_ips),
            "| users=", ",".join(d.users),
        )


asyncio.run(main())
