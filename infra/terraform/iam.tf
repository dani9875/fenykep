data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "fn" {
  for_each = local.functions

  name               = "${var.name_prefix}-${replace(each.key, "_", "-")}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# CloudWatch Logs írás — ez mindegyik függvénynek kell.
resource "aws_iam_role_policy_attachment" "basic" {
  for_each = local.functions

  role       = aws_iam_role.fn[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ── Jogosultság-csomagok ────────────────────────────────────────────────
#
# Minden függvény csak azt kapja meg, amire tényleg szüksége van
# (lásd a functions map "policies" mezőjét a lambda.tf-ben).

data "aws_iam_policy_document" "dynamo" {
  statement {
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
    ]
    resources = [
      aws_dynamodb_table.orders.arn,
      "${aws_dynamodb_table.orders.arn}/index/*",
    ]
  }
}

data "aws_iam_policy_document" "s3_uploads" {
  # A presigned URL aláírásához a függvénynek magának is joga kell legyen
  # arra a műveletre, amit aláír.
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.uploads.arn}/uploads/*"]
  }
}

data "aws_iam_policy_document" "s3_cache" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.uploads.arn}/cache/*"]
  }

  # ListBucket nélkül az S3 egy NEM LÉTEZŐ kulcsra AccessDenied-et ad
  # NoSuchKey helyett — így az első, üres cache-es hívás elszállna.
  # A jog a bucketre szól (nem objektumra), ezért külön statement.
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.uploads.arn]
  }
}

data "aws_iam_policy_document" "rate_limit" {
  statement {
    actions   = ["dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.rate_limit.arn]
  }
}

data "aws_iam_policy_document" "ses" {
  statement {
    actions   = ["ses:SendEmail", "ses:SendRawEmail"]
    resources = [aws_ses_email_identity.from.arn]

    # Csak a saját feladó címünkről mehet levél, akkor is, ha a kód
    # valamiért mást próbálna beállítani.
    condition {
      test     = "StringEquals"
      variable = "ses:FromAddress"
      values   = [var.ses_from_address]
    }
  }
}

locals {
  policy_json = {
    dynamo     = data.aws_iam_policy_document.dynamo.json
    s3_uploads = data.aws_iam_policy_document.s3_uploads.json
    s3_cache   = data.aws_iam_policy_document.s3_cache.json
    rate_limit = data.aws_iam_policy_document.rate_limit.json
    ses        = data.aws_iam_policy_document.ses.json
  }

  # "függvény:csomag" párok kilapítva, hogy for_each-elni lehessen.
  function_policies = merge([
    for fn_name, fn in local.functions : {
      for policy in fn.policies : "${fn_name}.${policy}" => {
        function = fn_name
        policy   = policy
      }
    }
  ]...)
}

resource "aws_iam_role_policy" "fn" {
  for_each = local.function_policies

  name   = each.value.policy
  role   = aws_iam_role.fn[each.value.function].id
  policy = local.policy_json[each.value.policy]
}
