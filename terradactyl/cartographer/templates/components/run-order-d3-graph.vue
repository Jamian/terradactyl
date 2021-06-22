Vue.component('run-order-graph', {
    template: `<div :style="{ position: 'relative' }">
    <svg id="run-graph" width="100%" height="300px">
    </svg>
  </div>`,
    props: ['data', 'selectedNode', 'state'],
    data() {
        return {
            width: 1024,
            height: 300,
            selections: {},
            simulation: null,
            pinY: 150,
            forceProperties: {
                center: {
                    x: 0.42,
                    y: 0.125
                },
                charge: {
                    enabled: true,
                    strength: -12000,
                    distanceMin: 1,
                    distanceMax: 15000
                },
                collide: {
                    enabled: true,
                    strength: 1,
                    iterations: 1,
                    radius: 30
                },
                forceX: {
                    enabled: true,
                    strength: 0.05,
                    x: 0.5
                },
                forceY: {
                    enabled: true,
                    strength: 1.5,
                    y: 0.5
                },
                link: {
                    enabled: true,
                    distance: 300,
                    iterations: 3
                }
            },
        }
    },
    computed: {
        nodes() { return this.data.nodes },
        links() { return this.data.links },
        // These are needed for captions
        linkTypes() {
            const linkTypes = []
            this.links.forEach(link => {
                if (linkTypes.indexOf(link.type) === -1)
                    linkTypes.push(link.type)
            })
            return linkTypes.sort()
        },
        classes() {
            const classes = []
            this.nodes.forEach(node => {
                if (classes.indexOf(node.class) === -1)
                    classes.push(node.class)
            })
            return classes.sort()
        },
    },
    created() {
        // You can set the component width and height in any way
        // you prefer. It's responsive! :)
        this.width = window.innerWidth
        this.height = window.innerHeight

        this.simulation = d3.forceSimulation()
            .force("link", d3.forceLink())
            .force("charge", d3.forceManyBody())
            .force("collide", d3.forceCollide())
            .force("center", d3.forceCenter())
            .force("forceX", d3.forceX())
            .force("forceY", d3.forceY())
            .on("tick", this.tick)
            // Call first time to setup default values
        this.updateForces()
    },
    mounted() {
        this.selections.svg = d3.select(this.$el.querySelector("#run-graph"))
        const svg = d3.select(this.$el.querySelector("#run-graph"))

        // Define the arrow marker
        svg.append("svg:defs").selectAll("marker")
            .data(["run-graph-end"]) // Different link/path types can be defined here
            .enter().append("svg:marker") // This section adds in the arrows
            .attr("id", String)
            .attr("viewBox", "0 -5 10 10")
            .attr("fill", "#6c757d")
            .attr("refX", 28) // Prevents arrowhead from being covered by circle
            .attr("refY", -2)
            .attr("markerWidth", 16)
            .attr("markerHeight", 16)
            .attr("orient", "auto")
            .append("svg:path")
            .attr("d", "M0,-5L10,0L0,5");

        // Add zoom
        svg.call(d3.zoom()
            .scaleExtent([1 / 4, 4])
            .on('zoom', this.zoomed))

        this.selections.graph = svg.append("g")
        const graph = this.selections.graph

        // Handle hovers on the run order graph
        this.$root.$on('nodeHover', stateData => {
            const circle = this.selections.graph.selectAll("circle")
            circle.classed('viewstate-hovered', false)
            circle.classed('viewstate-selected', false)
            circle.filter((d) => d.name === stateData.name).each(function(d) {
                if (!this.selectedNode) {
                    // If no selected node. Select this one.
                    this.selectedNode = d;
                    circle.filter((td) => (td === d) && (td['name'] != this.state))
                        .classed('viewstate-hovered', true)
                } else {
                    // Check if the node selected is the currently selected.
                    if (d == this.selectedNode) {
                        // Unpin the selected node.
                        circle.filter((td) => (td === d) && (td['name'] != this.state))
                            .classed('viewstate-hovered', true)
                        this.selectedNode = false
                    } else {
                        this.selectedNode = d
                        circle.classed('viewstate-selected', false)
                        circle.filter((td) => (td === d) && (td['name'] != this.state))
                            .classed('viewstate-hovered', true)
                    }
                }
            })
        })
        this.updateForces()
    },
    methods: {
        tick() {
            // If no data is passed to the Vue component, do nothing
            if (!this.data) { return }

            const transform = d => {
                return "translate(" + d.x + "," + this.pinY + ")"
            }

            const link = d => {
                // return "M" + d.source.x + "," + this.pinY + " L" + d.target.x + "," + this.pinY;
                var dx = d.target.x - d.source.x,
                    dy = this.pinY,
                    dr = Math.sqrt(dx * dx + dy * dy);
                return "M" +
                    d.source.x + "," +
                    this.pinY + "A" +
                    dr + "," + dr + " 0 0,1 " +
                    d.target.x + "," +
                    this.pinY;
            }

            // Highlight the currently viewed state node
            // TODO : Only really need to do this once, not every tick().
            const circle = this.selections.graph.selectAll("circle")
            circle.filter((td) => td['name'] == this.state)
                .classed('current-state', true)

            const graph = this.selections.graph
            graph.selectAll("path").attr("d", link)
            graph.selectAll("circle").attr("transform", transform)
            graph.selectAll("text").attr("transform", transform)
        },
        updateData() {
            this.simulation.nodes(this.nodes)
            this.simulation.force("link").links(this.links)

            const simulation = this.simulation
            const graph = this.selections.graph

            // Links should only exit if not needed anymore
            graph.selectAll("path")
                .data(this.links)
                .exit().remove()

            graph.selectAll("path")
                .data(this.links)
                .enter().append("path")
                .attr("class", d => "link " + d.type)

            // Nodes should always be redrawn to avoid lines above them
            graph.selectAll("circle").remove()
            graph.selectAll("circle")
                .data(this.nodes)
                .enter().append("circle")
                .attr("r", 30)
                .attr("class", d => d.class)
                .call(d3.drag()
                    .on('start', this.nodeDragStarted)
                    .on('drag', this.nodeDragged)
                    .on('end', this.nodeDragEnded))
                .on('mouseover', this.nodeMouseOver)
                .on('mouseout', this.nodeMouseOut)
                .on('click', this.nodeClick)

            graph.selectAll("text").remove()

            flipText = true
            textOffset = "45px"

            graph.selectAll("text")
                .data(this.nodes)
                .enter().append("text")
                .attr("x", 0)
                .attr("y", d => {
                    if (flipText) {
                        v = textOffset
                    } else {
                        v = "-" + textOffset
                    }
                    flipText = !flipText
                    return v
                })
                .attr("text-anchor", "middle")
                .text(d => d.name)

            // Add 'marker-end' attribute to each path
            const svg = d3.select(this.$el.querySelector("#run-graph"))
            svg.selectAll("g").selectAll("path").attr("marker-end", d => {
                // Caption items doesn't have source and target
                if (d.source && d.target &&
                    d.source.index === d.target.index) return "url(#ro-end-self)";
                else return "url(#run-graph-end)";
            });

            // Update caption every time data changes
            simulation.force("link")
                .distance(this.forceProperties.link.distance * simulation.nodes.length)
                .iterations(this.forceProperties.link.iterations)
            simulation.alpha(1).restart()
        },
        updateForces() {
            const { simulation, forceProperties, width, height } = this
            simulation.force("center")
                .x(width * forceProperties.center.x)
                .y(height * forceProperties.center.y)
            simulation.force("charge")
                .strength(forceProperties.charge.strength * forceProperties.charge.enabled)
                .distanceMin(forceProperties.charge.distanceMin)
                .distanceMax(forceProperties.charge.distanceMax)
            simulation.force("collide")
                .strength(forceProperties.collide.strength * forceProperties.collide.enabled)
                .radius(forceProperties.collide.radius)
                .iterations(forceProperties.collide.iterations)
            simulation.force("forceX")
                .strength(forceProperties.forceX.strength * forceProperties.forceX.enabled)
                .x(width * forceProperties.forceX.x)
                // simulation.force("forceY")
                //     .strength(forceProperties.forceY.strength * forceProperties.forceY.enabled)
                //     .y(height * forceProperties.forceY.y)
            simulation.force("link")
                .distance(forceProperties.link.distance)
                .iterations(forceProperties.link.iterations)

            // updates ignored until this is run
            // restarts the simulation (important if simulation has already slowed down)
            simulation.alpha(1).restart()
        },
        zoomed() {
            const transform = d3.event.transform
            this.selections.graph.attr('transform', transform)

            // Define some world boundaries based on the graph total size
            // so we don't scroll indefinitely
            const graphBox = this.selections.graph.node().getBBox()
            const margin = 200
            const worldTopLeft = [graphBox.x - margin, graphBox.y - margin]
            const worldBottomRight = [
                graphBox.x + graphBox.width + margin,
                graphBox.y + graphBox.height + margin
            ]
        },
        nodeDragStarted(d) {
            if (!d3.event.active) { this.simulation.alphaTarget(0.3).restart() }
            d.fx = d.x
            d.fy = d.y
        },
        nodeDragged(d) {
            d.fx = d3.event.x
            d.fy = d3.event.y
        },
        nodeDragEnded(d) {
            if (!d3.event.active) { this.simulation.alphaTarget(0.0001) }
            d.fx = null
            d.fy = null
        },
        nodeMouseOver(d) {
            const graph = this.selections.graph
            const circle = graph.selectAll("circle")
            const path = graph.selectAll("path")
            const text = graph.selectAll("text")

            circle.classed('viewstate-selected', false)
            circle.filter(
                    (td) => !(d['depends_on'].includes(td.name))
                )
                .classed('highlight', false)
                .classed('faded', true)
            path.classed('faded', true)

            circle.filter(
                    (td) => td === d
                ).classed('highlight', true)
                .classed('faded', false)

            if (!this.selectedNode) {
                const circle = this.selections.graph.selectAll("circle")
                circle.classed('viewstate-hovered', false)
                circle.filter((td) => td === d)
                    .classed('viewstate-hovered', true)

                this.$root.$emit('nodeHover', d)
            }
            // This ensures that tick is called so the node count is updated
            this.simulation.alphaTarget(0.0001).restart()
        },
        nodeMouseOut(d) {
            const graph = this.selections.graph
            const circle = graph.selectAll("circle")
            const path = graph.selectAll("path")
            const text = graph.selectAll("text")

            circle.classed('faded', false)
            circle.classed('highlight', false)
            path.classed('faded', false)
            path.classed('highlight', false)
            text.classed('faded', false)
            text.classed('highlight', false)
                // This ensures that tick is called so the node count is updated
            this.simulation.restart()
        },
        nodeClick(d) {
            const circle = this.selections.graph.selectAll("circle")
            circle.classed('viewstate-selected', false)
            circle.filter(
                    (td) => d['depends_on'].includes(td.name)
                )
                .classed('viewstate-selected', true)
            this.$root.$emit('nodeClick', d)
        },
    },
    watch: {
        data: {
            handler(newData) {
                this.updateData()
            },
            deep: true
        },
        forceProperties: {
            handler(newForce) {
                this.updateForces()
            },
            deep: true
        }
    }
})