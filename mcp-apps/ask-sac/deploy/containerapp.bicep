// SAC (Analytics Cloud) MCP Container App Deployment Template
targetScope = 'resourceGroup'

param appName string = 'velora-mcp-sac'
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
param sacClientSecretUrl string
param sacClientId string = 'velora-sac-client'

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
        targetPort: 8084
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
        { name: 'sac-client-secret', keyVaultUrl: sacClientSecretUrl, identity: userAssignedIdentityId }
      ]
    }
    template: {
      scale: { minReplicas: 1, maxReplicas: 2 }
      containers: [
        {
          name: 'sac-analytics'
          image: image
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'PORT', value: '8084' }
            { name: 'ALLOW_ANONYMOUS', value: 'false' }
            { name: 'DEMO_MODE', value: 'false' }
            { name: 'ALLOWED_HOSTS', value: allowedHosts }
            { name: 'PUBLIC_BASE_URL', value: publicBaseUrl }
            { name: 'MCP_API_KEY', secretRef: 'mcp-api-key' }
            { name: 'SAC_AUTH_MODE', value: 'oauth' }
            { name: 'SAC_CLIENT_ID', value: sacClientId }
            { name: 'SAC_CLIENT_SECRET', secretRef: 'sac-client-secret' }
          ]
          probes: [
            {
              type: 'Startup'
              httpGet: { path: '/health', port: 8084, scheme: 'HTTP' }
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 24
            }
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8084, scheme: 'HTTP' }
              initialDelaySeconds: 10
              periodSeconds: 30
              timeoutSeconds: 3
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8084, scheme: 'HTTP' }
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
