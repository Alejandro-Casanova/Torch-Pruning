from .dependency import TORCH_CONV, TORCH_BATCHNORM, TORCH_PRELU, TORCH_LINEAR
from .dependency import _module2type
import torch, thop

def count_prunable_params_of_modules(module):
    if isinstance( module, ( TORCH_CONV, TORCH_LINEAR) ):
        num_params = module.weight.numel()
        if module.bias is not None:
            num_params += module.bias.numel()
        return num_params
    elif isinstance( module, TORCH_BATCHNORM ):
        num_params = module.running_mean.numel() + module.running_var.numel()
        if module.affine:
            num_params+= module.weight.numel() + module.bias.numel()
        return num_params
    elif isinstance( module, TORCH_PRELU ):
        if len( module.weight )==1:
            return 0
        else:
            return module.weight.numel
    else:
        return 0

def count_prunable_in_channels(module):
    if isinstance( module, TORCH_CONV ):
        return module.weight.shape[1]
    elif isinstance( module, TORCH_LINEAR ):
        return module.in_features
    elif isinstance( module, TORCH_BATCHNORM ):
        return module.num_features
    elif isinstance( module, TORCH_PRELU ):
        if len( module.weight )==1:
            return 0
        else:
            return len(module.weight)
    else:
        return 0

def count_prunable_out_channels(module):
    if isinstance( module, TORCH_CONV ):
        return module.weight.shape[0]
    elif isinstance( module, TORCH_LINEAR ):
        return module.out_features
    elif isinstance( module, TORCH_BATCHNORM ):
        return module.num_features
    elif isinstance( module, TORCH_PRELU ):
        if len( module.weight )==1:
            return 0
        else:
            return len(module.weight)
    else:
        return 0

def count_params(module):
    return sum([ p.numel() for p in module.parameters() ])

def count_macs_and_params(model, input_size, example_inputs=None, device=None):
    if example_inputs is None:
        example_inputs = torch.randn(*input_size)
    if device is not None:
        example_inputs = example_inputs.to(device)
    macs, params = thop.profile(model, inputs=(example_inputs, ), verbose=False)
    return macs, params

def count_total_prunable_channels(model):
    in_ch = 0
    out_ch = 0
    for m in model.modules():
        out_ch+=count_prunable_out_channels(m)
        in_ch+= count_prunable_in_channels(m)
    return out_ch, in_ch
    
def draw_computational_graph(DG, save_as, title='Dependency Graph', figsize=(16, 16), dpi=200, cmap=None):
    import numpy as np
    import matplotlib.pyplot as plt
    n_nodes = len(DG.module2node)
    module2idx = { m: i for (i, m) in enumerate(DG.module2node.keys()) }
    G = np.zeros((n_nodes, n_nodes))
    fill_value = 1
    for module, node in DG.module2node.items():
        for input_node in node.inputs:
            G[ module2idx[input_node.module], module2idx[node.module] ] = fill_value
            G[ module2idx[node.module], module2idx[input_node.module] ] = fill_value
        for out_node in node.outputs:
            G[ module2idx[out_node.module], module2idx[node.module] ] = fill_value
            G[ module2idx[node.module], module2idx[out_node.module] ] = fill_value
        fns = DG.PRUNING_FN[_module2type(module)]
        if fns[0] == fns[1]:
            G[ module2idx[node.module], module2idx[node.module] ] = fill_value
    fig, ax = plt.subplots(figsize=(figsize))
    ax.imshow(G, cmap=cmap if cmap is not None else plt.get_cmap('Blues'))
    plt.hlines(y=np.arange(0, n_nodes)+0.5, xmin=np.full(n_nodes, 0)-0.5, xmax=np.full(n_nodes, n_nodes)-0.5, color="#444444", linewidth=0.1)
    plt.vlines(x=np.arange(0, n_nodes)+0.5, ymin=np.full(n_nodes, 0)-0.5, ymax=np.full(n_nodes, n_nodes)-0.5, color="#444444", linewidth=0.1)
    ax.set_title(title)
    fig.tight_layout()
    plt.savefig(save_as, dpi=dpi)
    return fig, ax

def draw_groups(DG, save_as, title='Group', figsize=(16, 16), dpi=200, cmap=None):
    import numpy as np
    import matplotlib.pyplot as plt
    n_nodes = 2*len(DG.module2node)
    node2idx = { m: i for (i, m) in enumerate(DG.module2node.values()) }
    G = np.zeros((n_nodes, n_nodes))
    fill_value=1
    for i, (module, node) in enumerate(DG.module2node.items()):
        group = DG.get_pruning_group(module, DG.PRUNING_FN[_module2type(module)][1], list(range(count_prunable_out_channels(module))))
        print(len(group))
        grouped_idxs = []
        for dep, _ in group:
            source, target, trigger, handler = dep.source, dep.target, dep.trigger, dep.handler
            if trigger in DG.out_channel_pruners:
                grouped_idxs.append(node2idx[source]*2+1)
            else:
                grouped_idxs.append(node2idx[source]*2)
            
            if handler in DG.out_channel_pruners:
                grouped_idxs.append(node2idx[target]*2+1)
            else:
                grouped_idxs.append(node2idx[target]*2)
        grouped_idxs = list(set(grouped_idxs))
        for k1 in grouped_idxs:
            for k2 in grouped_idxs:
                G[ k1, k2 ] = fill_value

    fig, ax = plt.subplots(figsize=(figsize))
    ax.imshow(G, cmap=cmap if cmap is not None else plt.get_cmap('Blues'))
    plt.hlines(y=np.arange(0, n_nodes)+0.5, xmin=np.full(n_nodes, 0)-0.5, xmax=np.full(n_nodes, n_nodes)-0.5, color="#444444", linewidth=0.1)
    plt.vlines(x=np.arange(0, n_nodes)+0.5, ymin=np.full(n_nodes, 0)-0.5, ymax=np.full(n_nodes, n_nodes)-0.5, color="#444444", linewidth=0.1)
    ax.set_title(title)
    fig.tight_layout()
    plt.savefig(save_as, dpi=dpi)
    return fig, ax

def draw_dependency_graph(DG, save_as, title='Group', figsize=(16, 16), dpi=200, cmap=None):
    import numpy as np
    import matplotlib.pyplot as plt
    n_nodes = len(DG.module2node)
    node2idx = { node: i for (i, node) in enumerate(DG.module2node.values()) }
    G = np.zeros((2*n_nodes, 2*n_nodes))
    fill_value=1
    for module, node in DG.module2node.items():
        for dep in node.dependencies:
            trigger = dep.trigger
            handler = dep.handler
            source = dep.source
            target = dep.target

            if trigger in DG.out_channel_pruners:
                G[ 2*node2idx[source]+1, 2*node2idx[target] ] = fill_value
            else:
                G[ 2*node2idx[source], 2*node2idx[target]+1 ] = fill_value
            
        fns = DG.PRUNING_FN[_module2type(module)]
        if fns[0]==fns[1]:
            G[ 2*node2idx[node], 2*node2idx[node]+1 ] = fill_value

    fig, ax = plt.subplots(figsize=(figsize))
    ax.imshow(G, cmap=cmap if cmap is not None else plt.get_cmap('Blues'))
    plt.hlines(y=np.arange(0, 2*n_nodes)+0.5, xmin=np.full(2*n_nodes, 0)-0.5, xmax=np.full(2*n_nodes, 2*n_nodes)-0.5, color="#444444", linewidth=0.1)
    plt.vlines(x=np.arange(0, 2*n_nodes)+0.5, ymin=np.full(2*n_nodes, 0)-0.5, ymax=np.full(2*n_nodes, 2*n_nodes)-0.5, color="#444444", linewidth=0.1)
    ax.set_title(title)
    fig.tight_layout()
    plt.savefig(save_as, dpi=dpi)
    return fig, ax


#def draw_dependency_graph(DG, save_as, title='Dependency Graph', figsize=(16, 16), dpi=200, cmap=None):
#    import numpy as np
#    import matplotlib.pyplot as plt
#    n_nodes = len(DG.module2node)
#    module2idx = { m: i for (i, m) in enumerate(DG.module2node.keys()) }
#    G = np.zeros((n_nodes, n_nodes))
#    fill_value = 1
#    for module, node in DG.module2node.items():
#        for input_node in node.inputs:
#            G[ module2idx[input_node.module], module2idx[node.module] ] = fill_value
#            G[ module2idx[node.module], module2idx[input_node.module] ] = fill_value
#        for out_node in node.outputs:
#            G[ module2idx[out_node.module], module2idx[node.module] ] = fill_value
#            G[ module2idx[node.module], module2idx[out_node.module] ] = fill_value
#        fns = DG.PRUNING_FN[_module2type(module)]
#        if fns[0] == fns[1]:
#            G[ module2idx[node.module], module2idx[node.module] ] = fill_value
#    fig, ax = plt.subplots(figsize=(figsize))
#    ax.imshow(G, cmap=cmap if cmap is not None else plt.get_cmap('Blues'))
#    plt.hlines(y=np.arange(0, n_nodes)+0.5, xmin=np.full(n_nodes, 0)-0.5, xmax=np.full(n_nodes, n_nodes)-0.5, color="#444444", linewidth=0.1)
#    plt.vlines(x=np.arange(0, n_nodes)+0.5, ymin=np.full(n_nodes, 0)-0.5, ymax=np.full(n_nodes, n_nodes)-0.5, color="#444444", linewidth=0.1)
#    ax.set_title(title)
#    fig.tight_layout()
#    plt.savefig(save_as, dpi=dpi)
#    return fig, ax
#
#def draw_groups(DG, save_as, title='Group', figsize=(16, 16), dpi=200, cmap=None):
#    import numpy as np
#    import matplotlib.pyplot as plt
#    n_nodes = len(DG.module2node)
#    module2idx = { m: i for (i, m) in enumerate(DG.module2node.keys()) }
#    G = np.zeros((n_nodes, n_nodes))
#    fill_value=1
#    for i, (module, node) in enumerate(DG.module2node.items()):
#        if not isinstance(module, tuple(DG.PRUNABLE_MODULES)):
#            continue
#        group = DG.get_pruning_group(module, DG.PRUNING_FN[_module2type(module)][1], list(range(count_prunable_out_channels(module))))
#        for dep, _ in group:
#            G[ module2idx[module], module2idx[dep.target.module] ] = fill_value
#    fig, ax = plt.subplots(figsize=(figsize))
#    ax.imshow(G, cmap=cmap if cmap is not None else plt.get_cmap('Blues'))
#    plt.hlines(y=np.arange(0, n_nodes)+0.5, xmin=np.full(n_nodes, 0)-0.5, xmax=np.full(n_nodes, n_nodes)-0.5, color="#444444", linewidth=0.1)
#    plt.vlines(x=np.arange(0, n_nodes)+0.5, ymin=np.full(n_nodes, 0)-0.5, ymax=np.full(n_nodes, n_nodes)-0.5, color="#444444", linewidth=0.1)
#    ax.set_title(title)
#    fig.tight_layout()
#    plt.savefig(save_as, dpi=dpi)
#    return fig, ax
