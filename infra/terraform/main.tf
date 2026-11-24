terraform {
  required_version = ">= 1.6"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {
    cognitive_account {
      purge_soft_delete_on_destroy = true
    }
  }
}

data "azurerm_client_config" "current" {}

locals {
  name = "${var.project}-${var.env}"
  tags = { project = var.project, env = var.env }
  adf  = jsondecode(file("${path.module}/../../adf/pipeline/pl_index_documents.json"))
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = local.tags
}

# ---------- storage: documents + pipeline state/logs ----------

resource "azurerm_storage_account" "data" {
  name                     = "st${var.project}${var.env}"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
  tags                     = local.tags
}

resource "azurerm_storage_container" "documents" {
  name                  = "documents"
  storage_account_id    = azurerm_storage_account.data.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "logs" {
  name                  = "pipeline-logs"
  storage_account_id    = azurerm_storage_account.data.id
  container_access_type = "private"
}

# ---------- AI services ----------

resource "azurerm_search_service" "search" {
  name                = "srch-${local.name}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = var.search_sku
  tags                = local.tags
}

resource "azurerm_cognitive_account" "openai" {
  name                  = "oai-${local.name}"
  resource_group_name   = azurerm_resource_group.rg.name
  location              = var.openai_location
  kind                  = "OpenAI"
  sku_name              = "S0"
  custom_subdomain_name = "oai-${local.name}"
  tags                  = local.tags
}

resource "azurerm_cognitive_deployment" "embedding" {
  name                 = "text-embedding-3-small"
  cognitive_account_id = azurerm_cognitive_account.openai.id
  model {
    format  = "OpenAI"
    name    = "text-embedding-3-small"
    version = "1"
  }
  sku {
    name     = "Standard"
    capacity = 50
  }
}

resource "azurerm_cognitive_deployment" "chat" {
  name                 = "gpt-4o-mini"
  cognitive_account_id = azurerm_cognitive_account.openai.id
  model {
    format  = "OpenAI"
    name    = "gpt-4o-mini"
    version = "2024-07-18"
  }
  sku {
    name     = "GlobalStandard"
    capacity = 20
  }
}

# used only for scanned PDFs that have no text layer
resource "azurerm_cognitive_account" "docintel" {
  name                  = "di-${local.name}"
  resource_group_name   = azurerm_resource_group.rg.name
  location              = azurerm_resource_group.rg.location
  kind                  = "FormRecognizer"
  sku_name              = "S0"
  custom_subdomain_name = "di-${local.name}"
  tags                  = local.tags
}

# ---------- secrets ----------

resource "azurerm_key_vault" "kv" {
  name                      = "kv-${local.name}"
  location                  = azurerm_resource_group.rg.location
  resource_group_name       = azurerm_resource_group.rg.name
  tenant_id                 = data.azurerm_client_config.current.tenant_id
  sku_name                  = "standard"
  enable_rbac_authorization = true
  tags                      = local.tags
}

resource "azurerm_role_assignment" "kv_admin" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# ---------- Function App ----------

resource "azurerm_application_insights" "ai" {
  name                = "appi-${local.name}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  application_type    = "web"
  tags                = local.tags
}

resource "azurerm_service_plan" "plan" {
  name                = "asp-${local.name}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  os_type             = "Linux"
  sku_name            = "Y1"
  tags                = local.tags
}

resource "azurerm_linux_function_app" "func" {
  name                       = "func-${local.name}"
  resource_group_name        = azurerm_resource_group.rg.name
  location                   = azurerm_resource_group.rg.location
  service_plan_id            = azurerm_service_plan.plan.id
  storage_account_name       = azurerm_storage_account.data.name
  storage_account_access_key = azurerm_storage_account.data.primary_access_key
  https_only                 = true

  identity {
    type = "SystemAssigned"
  }

  site_config {
    application_insights_connection_string = azurerm_application_insights.ai.connection_string
    application_stack {
      python_version = "3.11"
    }
  }

  app_settings = {
    DOCPIPE_BACKEND                     = "azure"
    DOCPIPE_EMBEDDER                    = "azure"
    DOCPIPE_BLOB_CONNECTION_STRING      = azurerm_storage_account.data.primary_connection_string
    DOCPIPE_BLOB_CONTAINER              = azurerm_storage_container.documents.name
    DOCPIPE_LOGS_CONTAINER              = azurerm_storage_container.logs.name
    DOCPIPE_SEARCH_ENDPOINT             = "https://${azurerm_search_service.search.name}.search.windows.net"
    DOCPIPE_SEARCH_KEY                  = azurerm_search_service.search.primary_key
    DOCPIPE_SEARCH_INDEX                = "documents"
    DOCPIPE_OPENAI_ENDPOINT             = azurerm_cognitive_account.openai.endpoint
    DOCPIPE_OPENAI_KEY                  = azurerm_cognitive_account.openai.primary_access_key
    DOCPIPE_OPENAI_EMBEDDING_DEPLOYMENT = azurerm_cognitive_deployment.embedding.name
    DOCPIPE_OPENAI_CHAT_DEPLOYMENT      = azurerm_cognitive_deployment.chat.name
    DOCPIPE_DOCINTEL_ENDPOINT           = azurerm_cognitive_account.docintel.endpoint
    DOCPIPE_DOCINTEL_KEY                = azurerm_cognitive_account.docintel.primary_access_key
  }

  tags = local.tags
}

data "azurerm_function_app_host_keys" "keys" {
  name                = azurerm_linux_function_app.func.name
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_key_vault_secret" "function_key" {
  name         = "function-key"
  value        = data.azurerm_function_app_host_keys.keys.default_function_key
  key_vault_id = azurerm_key_vault.kv.id
  depends_on   = [azurerm_role_assignment.kv_admin]
}

# ---------- Data Factory ----------

resource "azurerm_data_factory" "adf" {
  name                = "adf-${local.name}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  identity {
    type = "SystemAssigned"
  }
  tags = local.tags
}

resource "azurerm_role_assignment" "adf_kv" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_data_factory.adf.identity[0].principal_id
}

resource "azurerm_data_factory_linked_service_key_vault" "kv" {
  name            = "ls_keyvault"
  data_factory_id = azurerm_data_factory.adf.id
  key_vault_id    = azurerm_key_vault.kv.id
}

resource "azurerm_data_factory_linked_service_azure_function" "func" {
  name            = "ls_function_docpipe"
  data_factory_id = azurerm_data_factory.adf.id
  url             = "https://${azurerm_linux_function_app.func.default_hostname}"
  key_vault_key {
    linked_service_name = azurerm_data_factory_linked_service_key_vault.kv.name
    secret_name         = azurerm_key_vault_secret.function_key.name
  }
}

resource "azurerm_data_factory_pipeline" "index" {
  name            = local.adf.name
  data_factory_id = azurerm_data_factory.adf.id
  description     = local.adf.properties.description
  concurrency     = 1
  parameters = {
    full    = "false"
    trigger = "manual"
  }
  activities_json = jsonencode(local.adf.properties.activities)
  depends_on      = [azurerm_data_factory_linked_service_azure_function.func]
}

resource "azurerm_data_factory_trigger_schedule" "hourly" {
  name            = "tr_hourly"
  data_factory_id = azurerm_data_factory.adf.id
  pipeline_name   = azurerm_data_factory_pipeline.index.name
  frequency       = "Hour"
  interval        = 1
  activated       = true
  pipeline_parameters = {
    full    = "false"
    trigger = "schedule"
  }
}

resource "azurerm_data_factory_trigger_blob_event" "uploaded" {
  name                  = "tr_document_uploaded"
  data_factory_id       = azurerm_data_factory.adf.id
  storage_account_id    = azurerm_storage_account.data.id
  events                = ["Microsoft.Storage.BlobCreated", "Microsoft.Storage.BlobDeleted"]
  blob_path_begins_with = "/documents/blobs/"
  ignore_empty_blobs    = true
  activated             = true

  pipeline {
    name = azurerm_data_factory_pipeline.index.name
    parameters = {
      full    = "false"
      trigger = "blob_event"
    }
  }
}
