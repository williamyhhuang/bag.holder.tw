terraform {
  # bucket 名稱須與 bootstrap 的 var.tf_state_bucket 一致
  backend "gcs" {
    bucket = "bag-holder-tf-state"
    prefix = "deployable/state"
  }
}
