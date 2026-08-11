# Trade Capture Authority

`TradeCaptureService` converts each distinct simulation execution fill into one immutable canonical trade. Platform UUIDs remain independent of provider references. `execution_id` and deterministic `source_event_id` enforce exactly-once capture; partial fills remain separate trades so no fill quantity is lost.
