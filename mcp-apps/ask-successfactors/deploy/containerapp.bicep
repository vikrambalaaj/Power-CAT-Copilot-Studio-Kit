// Deployment template only. Requires an existing environment, identity and vault.
targetScope = 'resourceGroup'

param appName string
param location string = resourceGroup().location
param managedEnvironmentId string
param userAssignedIdentityId string
param registryServer string
@description('Use the ACR repository@sha256:digest reference from the release record.')
param image string
@description('Enable only when the approved gateway/network design requires it.')
param externalIngress bool = false
param publicBaseUrl string
param allowedHosts string
param sfApiUrl string
param sfCompanyId string
param sfUsernameSecretUrl string
param sfPasswordSecretUrl string
param mcpApiKeySecretUrl string
param approvalHmacSecretUrl string
param dataverseUrl string
param dataverseTenantId string
param dataverseClientId string
param dataverseClientSecretUrl string
@description('An approved business target; no default regulatory claim.')
param emiratisationTarget string
@description('Optional Azure File volume mount name for durable state in Container Apps.')
param storageVolumeName string = ''
param volumeMountPath string = '/mnt/velora'

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: managedEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: externalIngress
        targetPort: 8082
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: registryServer
          identity: userAssignedIdentityId
        }
      ]
      secrets: [
        { name: 'sf-username', keyVaultUrl: sfUsernameSecretUrl, identity: userAssignedIdentityId }
        { name: 'sf-password', keyVaultUrl: sfPasswordSecretUrl, identity: userAssignedIdentityId }
        { name: 'mcp-api-key', keyVaultUrl: mcpApiKeySecretUrl, identity: userAssignedIdentityId }
        { name: 'approval-hmac', keyVaultUrl: approvalHmacSecretUrl, identity: userAssignedIdentityId }
        { name: 'dataverse-client-secret', keyVaultUrl: dataverseClientSecretUrl, identity: userAssignedIdentityId }
      ]
    }
    template: {
      // In-process MCP sessions and chart storage are not shared across replicas.
      scale: { minReplicas: 1, maxReplicas: 1 }
      volumes: !empty(storageVolumeName) ? [
        {
          name: storageVolumeName
          storageType: 'AzureFile'
          storageName: storageVolumeName
        }
      ] : []
      containers: [
        {
          name: 'successfactors'
          image: image
          resources: { cpu: json('0.5'), memory: '1Gi' }
          volumeMounts: !empty(storageVolumeName) ? [
            {
              volumeName: storageVolumeName
              mountPath: volumeMountPath
            }
          ] : []
          env: [
            { name: 'PORT', value: '8082' }
            { name: 'ALLOW_ANONYMOUS', value: 'false' }
            { name: 'ENABLE_MUTATING_TOOLS', value: 'false' }
            { name: 'ENABLE_PERSONAL_INFO_TOOL', value: 'false' }
            { name: 'ENFORCE_CONSENT_GATE', value: 'true' }
            { name: 'MCP_FILE_LOG', value: '0' }
            { name: 'CORS_ORIGINS', value: '' }
            { name: 'ALLOWED_HOSTS', value: allowedHosts }
            { name: 'PUBLIC_BASE_URL', value: publicBaseUrl }
            { name: 'SF_API_URL', value: sfApiUrl }
            { name: 'SF_COMPANY_ID', value: sfCompanyId }
            { name: 'SF_USERNAME', secretRef: 'sf-username' }
            { name: 'SF_PASSWORD', secretRef: 'sf-password' }
            { name: 'MCP_API_KEY', secretRef: 'mcp-api-key' }
            { name: 'VELORA_APPROVAL_HMAC_SECRET', secretRef: 'approval-hmac' }
            { name: 'SF_EMIRATISATION_TARGET', value: emiratisationTarget }
            { name: 'DATAVERSE_URL', value: dataverseUrl }
            { name: 'AZURE_TENANT_ID', value: dataverseTenantId }
            { name: 'AZURE_CLIENT_ID', value: dataverseClientId }
            { name: 'AZURE_CLIENT_SECRET', secretRef: 'dataverse-client-secret' }
            { name: 'AZURE_STORAGE_MOUNT_PATH', value: !empty(storageVolumeName) ? '${volumeMountPath}/sf' : '' }
          ]
          probes: [
            {
              type: 'Startup'
              httpGet: { path: '/health', port: 8082, scheme: 'HTTP' }
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 24
            }
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8082, scheme: 'HTTP' }
              initialDelaySeconds: 10
              periodSeconds: 30
              timeoutSeconds: 3
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8082, scheme: 'HTTP' }
              periodSeconds: 10
              timeoutSeconds: 3
              failureThreshold: 3
            }
          ]
        }
      ]
    }
  }
}

output fqdn string = app.properties.configuration.ingress.fqdn
output deployedImage string = image
