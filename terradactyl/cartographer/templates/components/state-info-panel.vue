Vue.component('state-info-panel', {
    delimiters: ['[[', ']]'],
    template: `<div class="card shadow mb-4 border-bottom">
      <div class="card-header py-3">
        <h6 class="m-0 font-weight-bold text-info">
          <i class="fas fa-dot-circle mr-1"></i>
          Node Info</h6>
      </div>
      <div class="card-body">
          <table class = "table">
            <tr>
              <th>State Name</th>
              <td>[[ stateName ]]</td>
            </tr>
            <tr>
              <th>Terraform Version</th>
              <td>[[ stateTFVersion ]] </td>
            </tr>
            <tr>
              <th>Total Dependencies</th>
              <td>[[ stateDependencies ]]</td>
            </tr>
            <tr>
              <th>Resource Count</th>
              <td>[[ stateResourceCount ]]</td>
            </tr>
            <tr>
              <th>Created At</th>
              <td>[[ workspaceCreatedAt ]]</td>
            </tr>
            <tr>
              <th>Serial</th>
              <td>[[ serial ]]</td>
            </tr>
            <tr><th></th><td></td></tr>
        </table>
      <div class="card-body" style="margin-top: -50px;">
        <div class="my-2"></div>
        <a :href="'/states/' + stateName" class="btn btn-primary btn-icon-split" style="margin-left: -1.2rem;" v-bind:class="{ disabled: viewRunPathBtnDisabled }">
            <span class="icon text-white-50" style="padding-top:10px"><i class="fas fa-play"></i></span>
            <span class="text">Explore</span>
        </a>
        <a target="_blank" :href="'https://app.terraform.io/app/{{ organization}}/workspaces/' + stateName" v-bind:class="{ disabled: viewRunPathBtnDisabled }" class="btn btn-info btn-icon-split">
            <span class="icon text-white-50" style="padding-top:10px"><i class="fas fa-external-link-alt"></i></span>
            <span class="text">View in Terraform Cloud</span>
        </a>
        </div>
      </div>
    </div>`,
    data() {
        return {
            stateName: 'Click a node to view state info.',
            stateTFVersion: '',
            stateDependencies: null,
            viewRunPathBtnDisabled: true,
            stateResourceCount: null,
            workspaceCreatedAt: '',
            serial: '',
        }
    },
    mounted() {
        this.$root.$on('nodeHover', stateData => {
            this.stateName = stateData['name']
            this.stateTFVersion = stateData['terraform_version']
            this.stateDependencies = stateData['dependency_count']
            this.viewRunPathBtnDisabled = false
            this.stateResourceCount = stateData['resource_count']
            this.serial = stateData['serial']
            this.workspaceCreatedAt = stateData['created_at']
        });
        this.$root.$on('nodeClick', stateData => {
            this.stateName = stateData['name']
            this.stateTFVersion = stateData['terraform_version']
            this.stateDependencies = stateData['dependency_count']
            this.viewRunPathBtnDisabled = false
            this.stateResourceCount = stateData['resource_count']
            this.serial = stateData['resource_count']
            this.workspaceCreatedAt = stateData['created_at']
        });
    }
})