// Productivity MCP Container App Deployment Template
targetScope = 'resourceGroup'

param appName string = 'velora-mcp-productivity'
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
param m365ClientId string = ''
param m365ClientSecretUrl string = ''
param m365TenantId string = ''
param dataverseUrl string = ''
param dataverseClientSecretUrl string = ''
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
        targetPort: 8080
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
        { name: 'm365-client-secret', keyVaultUrl: m365ClientSecretUrl, identity: userAssignedIdentityId }
        { name: 'dataverse-client-secret', keyVaultUrl: dataverseClientSecretUrl, identity: userAssignedIdentityId }
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
          name: 'productivity'
          image: image
          resources: { cpu: json('0.5'), memory: '1Gi' }
          volumeMounts: !empty(storageVolumeName) ? [
            {
              volumeName: storageVolumeName
              mountPath: volumeMountPath
            }
          ] : []
          env: [
            { name: 'PORT', value: '8080' }
            { name: 'ALLOW_ANONYMOUS', value: 'false' }
            { name: 'ALLOWED_HOSTS', value: allowedHosts }
            { name: 'PUBLIC_BASE_URL', value: publicBaseUrl }
            { name: 'GRAPH_CLIENT_ID', value: m365ClientId }
            { name: 'GRAPH_TENANT_ID', value: m365TenantId }
            { name: 'GRAPH_CLIENT_SECRET', secretRef: 'm365-client-secret' }
            { name: 'GRAPH_API_URL', value: 'https://graph.microsoft.com/v1.0' }
            { name: 'M365_CLIENT_ID', value: m365ClientId }
            { name: 'M365_CLIENT_SECRET', secretRef: 'm365-client-secret' }
            { name: 'M365_TENANT_ID', value: m365TenantId }
            { name: 'AZURE_CLIENT_ID', value: m365ClientId }
            { name: 'AZURE_CLIENT_SECRET', secretRef: 'm365-client-secret' }
            { name: 'AZURE_TENANT_ID', value: m365TenantId }
            { name: 'DATAVERSE_URL', value: dataverseUrl }
            { name: 'DATAVERSE_CLIENT_SECRET', secretRef: 'dataverse-client-secret' }
            { name: 'VELORA_OUTBOX_DIR', value: '${volumeMountPath}/outbox' }
            { name: 'AZURE_STORAGE_MOUNT_PATH', value: '${volumeMountPath}/outbox' }
          ]
          probes: [
            {
              type: 'Startup'
              httpGet: { path: '/health', port: 8080, scheme: 'HTTP' }
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 24
            }
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8080, scheme: 'HTTP' }
              initialDelaySeconds: 10
              periodSeconds: 30
              timeoutSeconds: 3
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8080, scheme: 'HTTP' }
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

resource workerJob 'Microsoft.App/jobs@2024-03-01' = {
  name: '${appName}-worker-job'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  properties: {
    environmentId: managedEnvironmentId
    configuration: {
      triggerType: 'Schedule'
      scheduleTriggerConfig: {
        cronExpression: '* * * * *'
        parallelism: 1
        replicaCompletionCount: 1
      }
      replicaTimeout: 300
      replicaRetryLimit: 1
      registries: [
        {
          server: registryServer
          identity: userAssignedIdentityId
        }
      ]
      secrets: [
        { name: 'mcp-api-key', keyVaultUrl: mcpApiKeySecretUrl, identity: userAssignedIdentityId }
        { name: 'm365-client-secret', keyVaultUrl: m365ClientSecretUrl, identity: userAssignedIdentityId }
        { name: 'dataverse-client-secret', keyVaultUrl: dataverseClientSecretUrl, identity: userAssignedIdentityId }
      ]
    }
    template: {
      volumes: !empty(storageVolumeName) ? [
        {
          name: storageVolumeName
          storageType: 'AzureFile'
          storageName: storageVolumeName
        }
      ] : []
      containers: [
        {
          name: 'worker'
          image: image
          command: [
            'python'
            '-m'
            'productivity_mcp.worker'
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          volumeMounts: !empty(storageVolumeName) ? [
            {
              volumeName: storageVolumeName
              mountPath: volumeMountPath
            }
          ] : []
          env: [
            { name: 'ALLOW_ANONYMOUS', value: 'false' }
            { name: 'GRAPH_CLIENT_ID', value: m365ClientId }
            { name: 'GRAPH_TENANT_ID', value: m365TenantId }
            { name: 'GRAPH_CLIENT_SECRET', secretRef: 'm365-client-secret' }
            { name: 'M365_CLIENT_ID', value: m365ClientId }
            { name: 'M365_CLIENT_SECRET', secretRef: 'm365-client-secret' }
            { name: 'M365_TENANT_ID', value: m365TenantId }
            { name: 'AZURE_CLIENT_ID', value: m365ClientId }
            { name: 'AZURE_CLIENT_SECRET', secretRef: 'm365-client-secret' }
            { name: 'AZURE_TENANT_ID', value: m365TenantId }
            { name: 'DATAVERSE_URL', value: dataverseUrl }
            { name: 'DATAVERSE_CLIENT_SECRET', secretRef: 'dataverse-client-secret' }
            { name: 'VELORA_OUTBOX_DIR', value: '${volumeMountPath}/outbox' }
            { name: 'AZURE_STORAGE_MOUNT_PATH', value: '${volumeMountPath}/outbox' }
            { name: 'VELORA_SUBSCRIPTION_DB', value: '${volumeMountPath}/velora_subscriptions.db' }
          ]
        }
      ]
    }
  }
}

output fqdn string = app.properties.configuration.ingress.fqdn
output deployedImage string = image
output workerJobName string = workerJob.name
