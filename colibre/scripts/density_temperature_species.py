"""
Makes a rho-T plot. Uses the swiftsimio library.
"""

import matplotlib.pyplot as plt
import numpy as np

from swiftsimio import load

from unyt import mh, cm
from matplotlib.colors import LogNorm, ListedColormap, BoundaryNorm
from matplotlib.animation import FuncAnimation
from matplotlib.cm import get_cmap

# Set the limits of the figure.
density_bounds = [10 ** (-9.5), 1e6]  # in nh/cm^3
temperature_bounds = [10 ** (0), 10 ** (9.5)]  # in K
specfracs_bounds = [1e-2, 1]  # In metal mass fraction
min_specfracs = specfracs_bounds[0]
bins = 256


def get_data(filename, prefix_rho, prefix_T, species):
    """
    Grabs the data (T in Kelvin and density in mh / cm^3).
    """

    data = load(filename)

    number_density = (
        getattr(data.gas, f"{prefix_rho}densities").to_physical() / mh
    ).to(cm ** -3)
    temperature = getattr(data.gas, f"{prefix_T}temperatures").to_physical().to("K")
    masses = data.gas.masses.to_physical().to("Msun")
    hfrac = data.gas.element_mass_fractions.hydrogen.to_physical()

    sfracs = getattr(data.gas.species_fractions, species) * hfrac
    if species == "H2":
        sfracs *= 2.0
    sfracs[sfracs < min_specfracs] = min_specfracs

    return number_density.value, temperature.value, sfracs.value, masses.value


def make_hist(
    filename,
    density_bounds,
    temperature_bounds,
    bins,
    prefix_rho="",
    prefix_T="",
    species="HI",
):
    """
    Makes the histogram for filename with bounds as lower, higher
    for the bins and "bins" the number of bins along each dimension.

    Also returns the edges for pcolormesh to use.
    """

    density_bins = np.logspace(
        np.log10(density_bounds[0]), np.log10(density_bounds[1]), bins
    )
    temperature_bins = np.logspace(
        np.log10(temperature_bounds[0]), np.log10(temperature_bounds[1]), bins
    )

    nH, T, D, Mg = get_data(filename, prefix_rho, prefix_T, species)

    H, density_edges, temperature_edges = np.histogram2d(
        nH, T, bins=[density_bins, temperature_bins], weights=D * Mg
    )
    H_norm, _, _ = np.histogram2d(
        nH, T, bins=[density_bins, temperature_bins], weights=Mg
    )

    # Avoid div/0
    mask = H_norm == 0.0
    H[mask] = None
    H_norm[mask] = 1.0

    return np.ma.array((H / H_norm).T, mask=mask.T), density_edges, temperature_edges


def setup_axes(number_of_simulations: int, prop_type="hydro"):
    """
    Creates the figure and axis object. Creates a grid of a x b subplots
    that add up to at least number_of_simulations.
    """

    sqrt_number_of_simulations = np.sqrt(number_of_simulations)
    horizontal_number = int(np.ceil(sqrt_number_of_simulations))
    # Ensure >= number_of_simulations plots in a grid
    vertical_number = int(np.ceil(number_of_simulations / horizontal_number))

    fig, ax = plt.subplots(
        vertical_number, horizontal_number, squeeze=True, sharex=True, sharey=True,
    )

    ax = np.array([ax]) if number_of_simulations == 1 else ax

    if horizontal_number * vertical_number > number_of_simulations:
        for axis in ax.flat[number_of_simulations:]:
            axis.axis("off")

    # Set all valid on bottom row to have the horizontal axis label.
    for axis in np.atleast_2d(ax)[:][-1]:
        if prop_type == "hydro":
            axis.set_xlabel("Density [$n_H$ cm$^{-3}$]")
        elif prop_type == "subgrid":
            axis.set_xlabel("Subgrid Physical Density [$n_H$ cm$^{-3}$]")
        else:
            raise Exception("Unrecognised property type.")
    for axis in np.atleast_2d(ax).T[:][0]:
        if prop_type == "hydro":
            axis.set_ylabel("Temperature [K]")
        elif prop_type == "subgrid":
            axis.set_ylabel("Subgrid Temperature [K]")

    ax.flat[0].loglog()

    return fig, ax


def make_single_image(
    filenames,
    names,
    number_of_simulations,
    density_bounds,
    temperature_bounds,
    bins,
    output_path,
    prop_type,
    species,
):
    """
    Makes a single plot of rho-T
    """

    if prop_type == "subgrid":
        prefix_rho = "subgrid_physical_"
        prefix_T = "subgrid_"
    else:
        prefix_rho = ""
        prefix_T = ""

    fig, ax = setup_axes(
        number_of_simulations=number_of_simulations, prop_type=prop_type
    )

    hists = []

    for filename in filenames:
        hist, d, T = make_hist(
            filename,
            density_bounds,
            temperature_bounds,
            bins,
            prefix_rho,
            prefix_T,
            species,
        )
        hists.append(hist)

    smap = get_cmap("cividis")
    ncols = 10
    collist = []
    for i in range(ncols):
        collist.append(smap(i / float(ncols - 1)))

    cmap = ListedColormap(collist)

    norm = BoundaryNorm(np.linspace(*np.log10(specfracs_bounds), ncols + 1), ncols)

    vmax = np.max([np.max(hist) for hist in hists])

    for hist, name, axis in zip(hists, names, ax.flat):
        mappable = axis.pcolormesh(d, T, np.log10(hist), cmap=cmap, norm=norm)
        axis.text(0.025, 0.975, name, ha="left", va="top", transform=axis.transAxes)

    fig.colorbar(mappable, ax=ax.ravel().tolist(), label=f"{species} Mass Fraction")
    fig.savefig(f"{output_path}/{prefix_T}density_temperature_{species}.png")
    return


if __name__ == "__main__":
    from swiftpipeline.argumentparser import ScriptArgumentParser

    arguments = ScriptArgumentParser(
        description="Basic density-temperature figure.",
        additional_arguments={"quantity_type": "hydro", "hydrogen_species": "HI"},
    )

    snapshot_filenames = [
        f"{directory}/{snapshot}"
        for directory, snapshot in zip(
            arguments.directory_list, arguments.snapshot_list
        )
    ]

    plt.style.use(arguments.stylesheet_location)

    make_single_image(
        filenames=snapshot_filenames,
        names=arguments.name_list,
        number_of_simulations=arguments.number_of_inputs,
        density_bounds=density_bounds,
        temperature_bounds=temperature_bounds,
        bins=bins,
        output_path=arguments.output_directory,
        prop_type=arguments.quantity_type,
        species=arguments.hydrogen_species,
    )