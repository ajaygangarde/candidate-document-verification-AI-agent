import time
import boto3
from pydantic import BaseModel
from recruitment.shared.config import settings
from recruitment.shared.logging import logger

bedrock = boto3.client("bedrock-runtime", region_name=settings.aws_region)


def converse(model_id: str, content: list[dict], schema: type[BaseModel]) -> tuple[BaseModel, float]:
    """Call Bedrock Converse with forced tool-use to guarantee structured output.

    content is a list of Converse content blocks, e.g.:
        [{"text": "..."}]                                  # plain prompt
        [{"document": {...}}, {"text": "..."}]             # PDF + prompt
        [{"image": {...}}, {"text": "..."}]                # image + prompt

    Returns a tuple: (instance of `schema`, execution_time_seconds)
    """
    start_time = time.time()
    response = bedrock.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": content}],
        toolConfig={
            "tools": [{
                "toolSpec": {
                    "name": schema.__name__,
                    "description": f"Return the extracted {schema.__name__}.",
                    "inputSchema": {"json": schema.model_json_schema()},
                }
            }],
            "toolChoice": {"tool": {"name": schema.__name__}},
        },
    )
    execution_time = time.time() - start_time
    blocks = response["output"]["message"]["content"]
    tool_use = next(b["toolUse"] for b in blocks if "toolUse" in b)
    result = schema(**tool_use["input"])
    return result, execution_time
