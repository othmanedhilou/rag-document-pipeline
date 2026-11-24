output "function_app_name" {
  value = azurerm_linux_function_app.func.name
}

output "function_app_url" {
  value = "https://${azurerm_linux_function_app.func.default_hostname}"
}

output "data_factory_name" {
  value = azurerm_data_factory.adf.name
}

output "storage_account" {
  value = azurerm_storage_account.data.name
}

output "search_endpoint" {
  value = "https://${azurerm_search_service.search.name}.search.windows.net"
}

output "storage_connection_string" {
  value     = azurerm_storage_account.data.primary_connection_string
  sensitive = true
}
