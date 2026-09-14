output "api_base_url" {
  description = "Az API alap-URL-je. Ezt teszi be a frontendbe a scripts/deploy-frontend.sh."
  value       = aws_apigatewayv2_api.api.api_endpoint
}

output "barion_callback_url" {
  description = "Ezt hívja a Barion állapotváltozáskor (a Lambda már ezzel van beállítva)."
  value       = local.barion_callback_url
}

output "barion_redirect_url" {
  description = "Ide tér vissza a vásárló a Barion fizetőoldaláról."
  value       = "${var.site_url}/koszonjuk.html"
}

output "uploads_bucket" {
  description = "A fotók és a Foxpost cache bucketje."
  value       = aws_s3_bucket.uploads.bucket
}

output "orders_table" {
  description = "A rendelések DynamoDB táblája."
  value       = aws_dynamodb_table.orders.name
}

output "lambda_function_names" {
  description = "A létrehozott Lambdák neve (loghoz, `aws logs tail`-hez)."
  value       = sort([for fn in aws_lambda_function.fn : fn.function_name])
}

output "ses_identities_to_verify" {
  description = "Ezekre a címekre ment megerősítő levél az AWS-től. Kattints rá mindegyikben."
  value = sort(distinct(concat(
    [aws_ses_email_identity.from.email],
    [for identity in aws_ses_email_identity.admin : identity.email],
    [for identity in aws_ses_email_identity.recipients : identity.email],
  )))
}

output "next_steps" {
  description = "Mi a teendő az apply után."
  value       = <<-EOT

    1. Hitelesítsd az SES címeket: nézd meg a postaládát, és kattints
       minden "Amazon Web Services – Email Address Verification" levélben.
       Ellenőrzés:
         aws ses get-identity-verification-attributes \
           --identities ${var.ses_from_address} \
           --profile ${var.aws_profile} --region ${var.region}

    2. Deployold a frontendet a mostani API URL-lel:
         ./scripts/deploy-frontend.sh

    3. A Barion admin felületén nem kell URL-t beállítani: a callback és a
       redirect a fizetés indításakor megy át, és már ezekre van állítva:
         callback: ${local.barion_callback_url}
         redirect: ${var.site_url}/koszonjuk.html

    4. Élesítés előtt: BARION_API_BASE -> https://api.barion.com, éles POSKey,
       és SES production access.
  EOT
}
