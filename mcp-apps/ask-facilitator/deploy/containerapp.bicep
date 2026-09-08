// Facilitator MCP Container App Deployment Template
targetScope = 'resourceGroup'

param appName string = 'velora-mcp-facilitator'
param location string = resourceGroup().location
param managedEnvironmentId string
param userAssignedIdentityId string
param registryServer string
@description('Use the ACR repository@sha256:digest reference from the release record.')
param image string
param externalIngress bool = false
param publicBaseUrl string = ''
param allowedHosts string = 'teams.microsoft.com,*.azurecontainerapps.io,localhost'
param mcpApiKeySecretUrl string
param entraTenantId string = '7d167021-f5e9-4331-9b75-d44d55a1ce9b'
param entraClientId string = '5d178cb2-251e-436c-b2ec-5f36021d2cf8'
param entraClientSecretUrl string
param svcSenderEmail string = 'svc_aiagent@velora.ae'
param storageVolumeName string = 'velorastate'
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
        targetPort: 8085
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
        { name: 'mcp-api-key', keyVaultUrl: mcpApiKeySecretUrl, identity: userAssignedIdentityId }
        { name: 'entra-client-secret', keyVaultUrl: entraClientSecretUrl, identity: userAssignedIdentityId }
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
          name: 'facilitator'
          image: image
          resources: { cpu: json('0.5'), memory: '1Gi' }
          volumeMounts: !empty(storageVolumeName) ? [
            {
              volumeName: storageVolumeName
              mountPath: volumeMountPath
            }
          ] : []
          env: [
            { name: 'PORT', value: '8085' }
            { name: 'ALLOW_ANONYMOUS', value: 'false' }
            { name: 'ALLOWED_HOSTS', value: allowedHosts }
            { name: 'PUBLIC_BASE_URL', value: publicBaseUrl }
            { name: 'MCP_API_KEY', secretRef: 'mcp-api-key' }
            { name: 'ENTRA_TENANT_ID', value: entraTenantId }
            { name: 'ENTRA_CLIENT_ID', value: entraClientId }
            { name: 'ENTRA_CLIENT_SECRET', secretRef: 'entra-client-secret' }
            { name: 'SVC_SENDER_EMAIL', value: svcSenderEmail }
            { name: 'FACILITATOR_STORAGE_DIR', value: '${volumeMountPath}/facilitator' }
            { name: 'AZURE_STORAGE_MOUNT_PATH', value: '${volumeMountPath}/facilitator' }
          ]
          probes: [
            {
              type: 'Startup'
              httpGet: { path: '/health', port: 8085, scheme: 'HTTP' }
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 24
            }
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8085, scheme: 'HTTP' }
              initialDelaySeconds: 10
              periodSeconds: 30
              timeoutSeconds: 3
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8085, scheme: 'HTTP' }
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
