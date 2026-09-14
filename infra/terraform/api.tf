# ── API Gateway (HTTP API) ──────────────────────────────────────────────

resource "aws_apigatewayv2_api" "api" {
  name          = "${var.name_prefix}-api"
  protocol_type = "HTTP"
  description   = "Fény·kép Stúdió API — a frontend a Cloudflare Pages-en fut, ez csak JSON-t szolgál ki."

  cors_configuration {
    # A böngésző csak ezekről az origin-ekről hívhatja. A Barion callback
    # nem böngészőből jön, azt a CORS nem érinti.
    allow_origins     = local.allowed_origins
    allow_methods     = ["GET", "POST", "OPTIONS"]
    allow_headers     = ["content-type"]
    max_age           = 600
    allow_credentials = false
  }
}

locals {
  # "METÓDUS /útvonal" => melyik függvény szolgálja ki
  routes = {
    "GET /products"         = "get_products"
    "POST /uploads"         = "get_upload_url"
    "POST /orders"          = "create_order"
    "GET /orders/{orderId}" = "get_order_status"
    "POST /barion-callback" = "barion_callback"
    "GET /foxpost-lockers"  = "get_foxpost_lockers"
    "POST /contact"         = "send_contact_message"
  }
}

resource "aws_apigatewayv2_integration" "fn" {
  for_each = local.functions

  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.fn[each.key].invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = each.value.timeout * 1000
}

resource "aws_apigatewayv2_route" "route" {
  for_each = local.routes

  api_id    = aws_apigatewayv2_api.api.id
  route_key = each.key
  target    = "integrations/${aws_apigatewayv2_integration.fn[each.value].id}"
}

resource "aws_lambda_permission" "apigw" {
  for_each = local.functions

  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fn[each.key].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

# A $default stage auto_deploy-jal: nincs külön "deploy" lépés, az
# api_endpoint maga a használható alap-URL (nincs /prod utótag).
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    # Dev-védelem: egy elszabadult szkript vagy végtelen ciklus ne
    # generáljon korlátlan Lambda-számlát.
    throttling_burst_limit = 50
    throttling_rate_limit  = 20
  }
}
