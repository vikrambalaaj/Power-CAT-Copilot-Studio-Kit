// Azure Storage Account and Container Apps Managed Environment Storage Mount
targetScope = 'resourceGroup'

param storageAccountName string
param location string = resourceGroup().location
param environmentName string
param fileShareName string = 'velorastate'
param queueNames array = [
  'velora-recommendations'
  'velora-delivery-outbox'
  'velora-audit-events'
]

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-01-01' = {
  parent: storage
  name: 'default'
}

resource fileShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-01-01' = {
  parent: fileService
  name: fileShareName
  properties: {
    shareQuota: 100
  }
}

resource queueService 'Microsoft.Storage/storageAccounts/queueServices@2023-01-01' = {
  parent: storage
  name: 'default'
}

resource queues 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-01-01' = [for qName in queueNames: {
  parent: queueService
  name: qName
}]

resource managedEnv 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: environmentName
}

resource envStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: managedEnv
  name: fileShareName
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: fileShare.name
      accessMode: 'ReadWrite'
    }
  }
}

output storageAccountId string = storage.id
output storageAccountName string = storage.name
output envStorageName string = envStorage.name
output fileShareName string = fileShare.name
