locals {
  lambda_root = "${path.module}/../../backend/lambda"
  common_dir  = "${local.lambda_root}/common"

  allowed_origins = distinct(concat([var.site_url], var.extra_allowed_origins))

  # A Barion a saját szervereiről hívja ezt — a cím már az API létrehozásakor
  # ismert (nem függ az integrációktól), ezért nincs körkörös függőség.
  barion_callback_url = "${aws_apigatewayv2_api.api.api_endpoint}/barion-callback"

  # Minden Lambdának ugyanaz a közös része: forrásmappa a backend/lambda alatt,
  # env változók, és hogy milyen jogosultság-csomagokat kap (lásd iam.tf).
  functions = {
    get_products = {
      # A katalógus statikus és olcsó: itt nem kell külön korlát,
      # az API Gateway útvonal-throttlingja bőven elég.
      timeout  = 10
      memory   = 256
      env      = {}
      policies = []
    }

    get_upload_url = {
      timeout  = 10
      memory   = 256
      env      = merge(local.guard_env, { UPLOADS_BUCKET = aws_s3_bucket.uploads.bucket })
      policies = ["s3_uploads", "rate_limit"]
    }

    get_foxpost_lockers = {
      # A teljes országos lista letöltése és feldolgozása percekig nem tart,
      # de 10 másodpercnél többet igen — és több memória gyorsabb CPU-t is jelent.
      timeout  = 30
      memory   = 512
      env      = merge(local.guard_env, { CACHE_BUCKET = aws_s3_bucket.uploads.bucket })
      policies = ["s3_cache", "rate_limit"]
    }

    create_order = {
      # A Barion Payment/Start hívás a mi timeoutunkon belül kell beférjen
      # (a kliens 15 mp-et vár rá), plusz az utalásos ág e-mailt is küld.
      timeout  = 25
      memory   = 512
      env      = merge(local.order_env, local.guard_env)
      policies = ["dynamo", "ses", "rate_limit"]
    }

    barion_callback = {
      # A Barion 15 másodpercen belül vár 200-at, különben újrahív.
      timeout  = 14
      memory   = 512
      env      = merge(local.order_env, local.guard_env)
      policies = ["dynamo", "ses", "rate_limit"]
    }

    get_order_status = {
      # Ez a függvény is egyeztethet a Barionnal és küldhet visszaigazolót,
      # ha az IPN elmaradt — ezért ugyanaz a környezete és joga.
      timeout  = 20
      memory   = 512
      env      = merge(local.order_env, local.guard_env)
      policies = ["dynamo", "ses", "rate_limit"]
    }

    send_contact_message = {
      timeout = 10
      memory  = 256
      env = merge(local.guard_env, {
        SES_FROM_ADDRESS = var.ses_from_address
        ADMIN_EMAIL      = var.admin_email
      })
      policies = ["ses", "rate_limit"]
    }
  }

  # Visszaélés elleni beállítások — minden publikus végpont megkapja.
  guard_env = {
    RATE_LIMIT_TABLE = aws_dynamodb_table.rate_limit.name
    ALLOWED_ORIGINS  = join(",", local.allowed_origins)
    ENFORCE_ORIGIN   = var.enforce_origin ? "true" : "false"
  }

  # A rendeléssel dolgozó három függvény környezete azonos.
  order_env = {
    ORDERS_TABLE           = aws_dynamodb_table.orders.name
    UPLOADS_BUCKET         = aws_s3_bucket.uploads.bucket
    SITE_BASE_URL          = var.site_url
    SES_FROM_ADDRESS       = var.ses_from_address
    ADMIN_EMAIL            = var.admin_email
    BANK_ACCOUNT_NAME      = var.bank_account_name
    BANK_ACCOUNT_NUMBER    = var.bank_account_number
    BARION_API_BASE        = var.barion_api_base
    BARION_POSKEY          = var.barion_poskey
    BARION_PAYEE           = var.barion_payee
    BARION_FUNDING_SOURCES = var.barion_funding_sources
    BARION_CALLBACK_URL    = local.barion_callback_url
    BARION_REDIRECT_URL    = "${var.site_url}/koszonjuk.html"
  }
}

# ── Közös modulok Lambda Layerként ──────────────────────────────────────
#
# A backend/lambda/common/*.py fájlok a Layer python/ mappájába kerülnek,
# így mindegyik függvény `import barion`-nal eléri őket. Nincs külön
# build lépés: a zipet a Terraform állítja elő a forrásból.

data "archive_file" "common_layer" {
  type        = "zip"
  output_path = "${path.module}/build/common-layer.zip"

  dynamic "source" {
    for_each = fileset(local.common_dir, "*.py")
    content {
      content  = file("${local.common_dir}/${source.value}")
      filename = "python/${source.value}"
    }
  }
}

resource "aws_lambda_layer_version" "common" {
  layer_name          = "${var.name_prefix}-common"
  description         = "products.py, dynamo.py, barion.py, payments.py, ses_mail.py"
  filename            = data.archive_file.common_layer.output_path
  source_code_hash    = data.archive_file.common_layer.output_base64sha256
  compatible_runtimes = ["python3.12"]
}

# ── Függvények ──────────────────────────────────────────────────────────

data "archive_file" "function" {
  for_each = local.functions

  type        = "zip"
  source_file = "${local.lambda_root}/${each.key}/handler.py"
  output_path = "${path.module}/build/${each.key}.zip"
}

resource "aws_lambda_function" "fn" {
  for_each = local.functions

  function_name    = "${var.name_prefix}-${replace(each.key, "_", "-")}"
  role             = aws_iam_role.fn[each.key].arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.function[each.key].output_path
  source_code_hash = data.archive_file.function[each.key].output_base64sha256
  timeout          = each.value.timeout
  memory_size      = each.value.memory
  layers           = [aws_lambda_layer_version.common.arn]

  environment {
    variables = each.value.env
  }

  # A log group nélkül a Lambda maga hozná létre, "soha nem jár le"
  # megőrzéssel. Így a Terraform kezeli, és 14 nap után törlődik.
  depends_on = [aws_cloudwatch_log_group.fn]
}

resource "aws_cloudwatch_log_group" "fn" {
  for_each = local.functions

  name              = "/aws/lambda/${var.name_prefix}-${replace(each.key, "_", "-")}"
  retention_in_days = var.log_retention_days
}
