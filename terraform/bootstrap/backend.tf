terraform {
  # Bootstrap 使用 local backend，因為它本身建立 GCS state bucket
  # 執行完後 state 檔保留在本機，不提交至 git
  backend "local" {
    path = "terraform.tfstate"
  }
}
