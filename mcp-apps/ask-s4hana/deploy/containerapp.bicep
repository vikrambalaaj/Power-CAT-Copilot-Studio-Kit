// S4HANA Finance MCP Container App Deployment Template
targetScope = 'resourceGroup'

param appName string = 'velora-mcp-s4hana'
param location string = resourceGroup().location
param managedEnvironmentId string
param userAssignedIdentityId string
param registryServer string
@description('Use the ACR repository@sha256:digest reference from the release record.')
param image string
param externalIngress bool = false
param publicBaseUrl string = 'https://agenticad-execai-dev-uaen-ca-001.niceisland-c61ec088.uaenorth.azurecontainerapps.io'
param allowedHosts string = 'fiori.velora.ae,*.azurecontainerapps.io,localhost'
param s4ApiUrl string = 'https://fiori.velora.ae/sap/opu/odata4/sap/zfi_sbn_ageingdata_srv/srvd_a2x/sap/zfi_sdf_ageingdata_srv/0001'
param s4UsernameSecretUrl string
param s4PasswordSecretUrl string
param mcpApiKeySecretUrl string
param approvalHmacSecretUrl string
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
        targetPort: 8083
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
        { name: 's4-username', keyVaultUrl: s4UsernameSecretUrl, identity: userAssignedIdentityId }
        { name: 's4-password', keyVaultUrl: s4PasswordSecretUrl, identity: userAssignedIdentityId }
        { name: 'mcp-api-key', keyVaultUrl: mcpApiKeySecretUrl, identity: userAssignedIdentityId }
        { name: 'approval-hmac', keyVaultUrl: approvalHmacSecretUrl, identity: userAssignedIdentityId }
      ]
    }
    template: {
      scale: { minReplicas: 1, maxReplicas: 2 }
      volumes: !empty(storageVolumeName) ? [
        {
          name: storageVolumeName
          storageType: 'AzureFile'
          storageName: storageVolumeName
        }
      ] : []
      containers: [
        {
          name: 's4hana-finance'
          image: image
          resources: { cpu: json('0.5'), memory: '1Gi' }
          volumeMounts: !empty(storageVolumeName) ? [
            {
              volumeName: storageVolumeName
              mountPath: volumeMountPath
            }
          ] : []
          env: [
            { name: 'PORT', value: '8083' }
            { name: 'ALLOW_ANONYMOUS', value: 'false' }
            { name: 'CORS_ORIGINS', value: '' }
            { name: 'ALLOWED_HOSTS', value: allowedHosts }
            { name: 'PUBLIC_BASE_URL', value: publicBaseUrl }
            { name: 'S4_API_URL', value: s4ApiUrl }
            { name: 'S4_AUTH_MODE', value: 'basic' }
            { name: 'S4_USERNAME', secretRef: 's4-username' }
            { name: 'S4_PASSWORD', secretRef: 's4-password' }
            { name: 'MCP_API_KEY', secretRef: 'mcp-api-key' }
            { name: 'VELORA_APPROVAL_HMAC_SECRET', secretRef: 'approval-hmac' }
            { name: 'S4_VERIFY_TLS', value: 'true' }
            { name: 'AZURE_STORAGE_MOUNT_PATH', value: !empty(storageVolumeName) ? '${volumeMountPath}/s4' : '' }
          ]
          probes: [
            {
              type: 'Startup'
              httpGet: { path: '/health', port: 8083, scheme: 'HTTP' }
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 24
            }
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8083, scheme: 'HTTP' }
              initialDelaySeconds: 10
              periodSeconds: 30
              timeoutSeconds: 3
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8083, scheme: 'HTTP' }
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
